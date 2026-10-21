"""Renderer DLNA giả (UPnP MediaRenderer:1) chạy ở 127.0.0.1 — fixture của test, KHÔNG phải
giao thức dùng thật. Chỉ trả lời khi ``enabled()`` đúng (mô phỏng "DLNA của loa đang bật"),
và ghi lại mọi hành động SOAP nhận được để test đối chiếu."""

import re
from xml.sax.saxutils import escape

from aiohttp import web

UDN = "uuid:r1-fake-0001"
_NS = {"AVT": "urn:schemas-upnp-org:service:AVTransport:1",
       "RC": "urn:schemas-upnp-org:service:RenderingControl:1",
       "CM": "urn:schemas-upnp-org:service:ConnectionManager:1"}
_PATH = {"AVT": "avt", "RC": "rc", "CM": "cm"}
_SID = {"AVT": "AVTransport", "RC": "RenderingControl", "CM": "ConnectionManager"}

#: dịch vụ -> {hành động: ([đối số vào], {đối số ra: giá trị})}
_ACTIONS = {
    "AVT": {
        "SetAVTransportURI": (["InstanceID", "CurrentURI", "CurrentURIMetaData"], {}),
        "Play": (["InstanceID", "Speed"], {}),
        "Stop": (["InstanceID"], {}),
        "Pause": (["InstanceID"], {}),
        "GetTransportInfo": (["InstanceID"], {
            "CurrentTransportState": "STOPPED", "CurrentTransportStatus": "OK",
            "CurrentSpeed": "1"}),
        "GetMediaInfo": (["InstanceID"], {
            "NrTracks": "0", "MediaDuration": "00:00:00", "CurrentURI": "",
            "CurrentURIMetaData": "", "NextURI": "", "NextURIMetaData": "",
            "PlayMedium": "NONE", "RecordMedium": "NOT_IMPLEMENTED",
            "WriteStatus": "NOT_IMPLEMENTED"}),
        "GetPositionInfo": (["InstanceID"], {
            "Track": "0", "TrackDuration": "00:00:00", "TrackMetaData": "",
            "TrackURI": "", "RelTime": "00:00:00", "AbsTime": "00:00:00",
            "RelCount": "0", "AbsCount": "0"}),
    },
    "RC": {
        "GetVolume": (["InstanceID", "Channel"], {"CurrentVolume": "50"}),
        "SetVolume": (["InstanceID", "Channel", "DesiredVolume"], {}),
        "GetMute": (["InstanceID", "Channel"], {"CurrentMute": "0"}),
        "SetMute": (["InstanceID", "Channel", "DesiredMute"], {}),
    },
    "CM": {
        "GetProtocolInfo": ([], {"Source": "", "Sink": "http-get:*:audio/mpeg:*,"
                                                       "http-get:*:audio/x-wav:*"}),
    },
}
_STATE_VARS = {
    "AVT": {"TransportState": "string", "TransportStatus": "string",
            "PlaybackStorageMedium": "string", "PossiblePlaybackStorageMedia": "string",
            "CurrentPlayMode": "string", "TransportPlaySpeed": "string",
            "NumberOfTracks": "ui4", "CurrentMediaDuration": "string",
            "AVTransportURI": "string", "AVTransportURIMetaData": "string",
            "NextAVTransportURI": "string", "NextAVTransportURIMetaData": "string",
            "CurrentTrack": "ui4", "CurrentTrackDuration": "string",
            "CurrentTrackMetaData": "string", "CurrentTrackURI": "string",
            "RelativeTimePosition": "string", "AbsoluteTimePosition": "string",
            "RelativeCounterPosition": "i4", "AbsoluteCounterPosition": "i4",
            "RecordStorageMedium": "string", "RecordMediumWriteStatus": "string",
            "A_ARG_TYPE_InstanceID": "ui4", "A_ARG_TYPE_Speed": "string"},
    "RC": {"Volume": "ui2", "Mute": "boolean", "A_ARG_TYPE_InstanceID": "ui4",
           "A_ARG_TYPE_Channel": "string"},
    "CM": {"SourceProtocolInfo": "string", "SinkProtocolInfo": "string"},
}
#: ánh xạ tên đối số -> biến trạng thái liên quan
_REL = {"AVT": {"InstanceID": "A_ARG_TYPE_InstanceID", "Speed": "A_ARG_TYPE_Speed",
                "CurrentURI": "AVTransportURI", "CurrentURIMetaData": "AVTransportURIMetaData",
                "CurrentTransportState": "TransportState",
                "CurrentTransportStatus": "TransportStatus", "CurrentSpeed": "TransportPlaySpeed",
                "NrTracks": "NumberOfTracks", "MediaDuration": "CurrentMediaDuration",
                "NextURI": "NextAVTransportURI", "NextURIMetaData": "NextAVTransportURIMetaData",
                "PlayMedium": "PlaybackStorageMedium", "RecordMedium": "RecordStorageMedium",
                "WriteStatus": "RecordMediumWriteStatus", "Track": "CurrentTrack",
                "TrackDuration": "CurrentTrackDuration", "TrackMetaData": "CurrentTrackMetaData",
                "TrackURI": "CurrentTrackURI", "RelTime": "RelativeTimePosition",
                "AbsTime": "AbsoluteTimePosition", "RelCount": "RelativeCounterPosition",
                "AbsCount": "AbsoluteCounterPosition"},
        "RC": {"InstanceID": "A_ARG_TYPE_InstanceID", "Channel": "A_ARG_TYPE_Channel",
               "CurrentVolume": "Volume", "DesiredVolume": "Volume",
               "CurrentMute": "Mute", "DesiredMute": "Mute"},
        "CM": {"Source": "SourceProtocolInfo", "Sink": "SinkProtocolInfo"}}


def _scpd(svc: str) -> str:
    actions = []
    for name, (ins, outs) in _ACTIONS[svc].items():
        args = "".join(f"<argument><name>{a}</name><direction>in</direction>"
                       f"<relatedStateVariable>{_REL[svc][a]}</relatedStateVariable></argument>"
                       for a in ins)
        args += "".join(f"<argument><name>{a}</name><direction>out</direction>"
                        f"<relatedStateVariable>{_REL[svc][a]}</relatedStateVariable></argument>"
                        for a in outs)
        actions.append(f"<action><name>{name}</name><argumentList>{args}</argumentList></action>")
    variables = "".join(
        f'<stateVariable sendEvents="{"no" if v.startswith("A_ARG") else "yes"}">'
        f"<name>{v}</name><dataType>{t}</dataType></stateVariable>"
        for v, t in _STATE_VARS[svc].items())
    return ('<?xml version="1.0"?><scpd xmlns="urn:schemas-upnp-org:service-1-0">'
            "<specVersion><major>1</major><minor>0</minor></specVersion>"
            f"<actionList>{''.join(actions)}</actionList>"
            f"<serviceStateTable>{variables}</serviceStateTable></scpd>")


def _description(base: str) -> str:
    services = "".join(
        f"<service><serviceType>{_NS[s]}</serviceType>"
        f"<serviceId>urn:upnp-org:serviceId:{_SID[s]}</serviceId>"
        f"<SCPDURL>/{_PATH[s]}.xml</SCPDURL><controlURL>/{_PATH[s]}/ctrl</controlURL>"
        f"<eventSubURL>/{_PATH[s]}/evt</eventSubURL></service>" for s in _NS)
    return ('<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0">'
            "<specVersion><major>1</major><minor>0</minor></specVersion>"
            f"<URLBase>{base}</URLBase><device>"
            "<deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>"
            "<friendlyName>R1 giả</friendlyName><manufacturer>Fake</manufacturer>"
            f"<modelName>FakeDMR</modelName><UDN>{UDN}</UDN>"
            f"<serviceList>{services}</serviceList></device></root>")


class FakeDMR:
    def __init__(self, enabled):
        self.enabled = enabled
        #: (hành động, {đối số: giá trị}) theo thứ tự nhận
        self.actions: list[tuple[str, dict[str, str]]] = []
        self.port = 0
        self._runner = None

    @property
    def location(self) -> str:
        return f"http://127.0.0.1:{self.port}/desc.xml"

    def called(self, action: str) -> list[dict[str, str]]:
        return [a for n, a in self.actions if n == action]

    async def _guard(self, handler, request):
        if not self.enabled():
            raise web.HTTPServiceUnavailable()
        return await handler(request)

    async def _desc(self, request):
        return web.Response(text=_description(f"http://127.0.0.1:{self.port}/"),
                            content_type="text/xml")

    def _scpd_handler(self, svc):
        async def handler(request):
            return web.Response(text=_scpd(svc), content_type="text/xml")
        return handler

    def _ctrl_handler(self, svc):
        async def handler(request):
            action = request.headers["SOAPAction"].strip('"').split("#")[-1]
            body = await request.text()
            args = {m.group(1): m.group(2) for m in re.finditer(
                r"<(\w+)>([^<]*)</\1>", body) if m.group(1) not in ("Body", "Envelope")}
            from html import unescape
            self.actions.append((action, {k: unescape(v) for k, v in args.items()}))
            outs = "".join(f"<{k}>{escape(v)}</{k}>"
                           for k, v in _ACTIONS[svc][action][1].items())
            xml = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/'
                   'envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
                   f'<s:Body><u:{action}Response xmlns:u="{_NS[svc]}">{outs}'
                   f"</u:{action}Response></s:Body></s:Envelope>")
            return web.Response(text=xml, content_type="text/xml")
        return handler

    async def start(self):
        @web.middleware
        async def mw(request, handler):
            return await self._guard(handler, request)

        app = web.Application(middlewares=[mw])
        app.router.add_get("/desc.xml", self._desc)
        for s in _NS:
            app.router.add_get(f"/{_PATH[s]}.xml", self._scpd_handler(s))
            app.router.add_post(f"/{_PATH[s]}/ctrl", self._ctrl_handler(s))
            # Không đăng ký SUBSCRIBE: aiohttp trả 405, dlna_dmr coi là "loa từ chối
            # đăng ký sự kiện" và chuyển sang hỏi định kỳ — đúng đường chấp nhận được.
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
