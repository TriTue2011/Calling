"""Hang so cua tich hop Zalo Call."""

DOMAIN = "zalo_call"

CONF_URL = "url"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_WEBHOOK_ID = "webhook_id"

# Tuy chon (options flow)
CONF_HA_URL = "ha_url"            # dia chi HA ma app 110 goi duoc (webhook)
CONF_AI_ENABLED = "ai_enabled"    # tu tra loi tin nhan 1-1 bang tro ly AI
CONF_AI_AGENT = "ai_agent"        # agent hoi thoai (de trong = mac dinh)
CONF_AI_THREADS = "ai_threads"    # chi tra loi cac threadId nay (rong = moi 1-1)
CONF_SPEAKER = "speaker"          # media_player phat tieng cuoc goi
CONF_MIC = "mic"                  # nguon mic cho cuoc goi
CONF_CAMERA = "camera"            # camera cho video call

# Su kien ban len bus cua HA
EVENT_PREFIX = DOMAIN + "_"       # zalo_call_message / zalo_call_call / ...
SCAN_INTERVAL_SECONDS = 10

# Cau noi am thanh cuoc goi (loa / mic / camera: mac dinh + ghi de moi cuoc goi)
CONF_MIC_URL = "mic_url"          # URL mic bat ky (rtsp/http...), thang CONF_MIC
EVENT_STATE = EVENT_PREFIX + "call_state"   # zalo_call_call_state: state + thiet bi
