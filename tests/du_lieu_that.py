"""Dữ liệu ĐO trên loa R1 thật, không tự nghĩ.

``get_eq_config`` trên cổng 8080 (khoá ``type``, ``code`` 200). Trường ``data`` của khung trả
về là CHUỖI JSON, đúng như dưới đây (đo 21/10/2026). Chỉ dùng làm fixture; không có địa chỉ
hay khoá nào trong đó.
"""

import json

GET_EQ_CONFIG_DATA = (
    '{"Mixer":{},"bass":{"Current_Strength":200,"Bass_Enable":false,"sound_effects_bass_enable":false},"eq":{"Preset_list":[{"Preset":0,"Name":"Normal"},{"Preset":1,"Name":"Classical"},{"Preset":2,"Name":"Dance"},{"Preset":3,"Name":"Flat"},{"Preset":4,"Name":"Folk"},{"Preset":5,"Name":"Heavy Metal"},{"Preset":6,"Name":"Hip Hop"},{"Preset":7,"Name":"Jazz"},{"Preset":8,"Name":"Pop"},{"Preset":9,"Name":"Rock"}],"Eq_Enable":true,"Current_Preset":-1,"sound_effects_eq_enable":true,"Bands":{"list":[{"Band":0,"BandLevel":200,"Frequency":60000},{"Band":1,"BandLevel":-400,"Frequency":230000},{"Band":2,"BandLevel":-100,"Frequency":910000},{"Band":3,"BandLevel":-500,"Frequency":3600000},{"Band":4,"BandLevel":100,"Frequency":14000000}],"minBandLevel":-1500,"maxBandLevel":1500}},"loudness":{"Loudness_Enable":false,"Current_Gain":200.0,"sound_effects_loudness_enable":false}}'
)

#: Khung đầy đủ như loa gửi.
GET_EQ_CONFIG_MSG = {"type": "get_eq_config", "code": 200, "msg": "ok",
                     "data": GET_EQ_CONFIG_DATA}

#: Dạng đã giải mã, để test so giá trị.
GET_EQ_CONFIG = json.loads(GET_EQ_CONFIG_DATA)
