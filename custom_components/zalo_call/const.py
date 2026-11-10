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

# Thiet bi mac dinh nam tren THIET BI (cac thuc the select/text/switch), luu bang
# Store cua HA — khong phai options (doi khong lam tai lai tich hop).
CONF_AUTO_MIC = "auto_mic"        # tu phat mic khi cuoc goi duoc nghe may
CONF_AUTO_VIDEO = "auto_video"    # ben kia xin len video: tu dong y + phat camera
CONF_ECHO_GUARD = "echo_guard"          # chong vong: auto | on | off
ECHO_MODES = ("auto", "on", "off")
CONF_AUTO_VIDEO_DELAY = "auto_video_delay"   # giay cho truoc khi tu dong y (0 = ngay)
MAX_AUTO_VIDEO_DELAY = 120
STORAGE_VERSION = 1
NONE_LABEL = "Không"
MIC_URL_LABEL = "URL (ô Mic URL)"
