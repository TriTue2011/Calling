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
CONF_AI_FORMAT = "ai_format"        # định dạng chữ của trả lời AI: plain | markdown (AI hay trả **đậm**, danh sách…)
CONF_AI_EMPHASIS = "ai_emphasis"    # tự nhấn mạnh số và chữ đậm bằng màu: off | red | orange | yellow | green
CONF_TEXT_AI_AGENT = "text_ai_agent"        # trợ lý hội thoại dùng cho chế độ auto (trống = trợ lý của AI tự trả lời, rồi trợ lý mặc định)
CONF_TEXT_AI_INLINE = "text_ai_inline"    # công tắc: AI tự trả lời định dạng NGAY TRONG lượt trả lời (nhúng chỉ dẫn, không gọi thêm); mặc định bật
CONF_TEXT_AI_SMART = "text_ai_smart"      # công tắc: send_message dùng AI đánh giá ngữ cảnh cho các mục auto (thêm vài giây); mặc định tắt
CONF_TEXT_AUTO_EMOJI = "text_auto_emoji"   # công tắc: tự thêm emoji hợp ngữ cảnh vào đầu từng dòng của MỌI tin tích hợp gửi (send_message, AI); bật/tắt
AI_FORMATS = ("plain", "markdown")
# Kiểu chữ mặc định cho MỌI tin tích hợp gửi (send_message, trả lời AI); send_message ghi đè từng tin. Mỗi mục có chế độ «auto».
CONF_TEXT_SIZE = "text_size"              # off | small | big | auto
CONF_TEXT_COLOR = "text_color"            # off | auto | red | orange | yellow | green
CONF_TEXT_BOLD = "text_bold"              # off | on | auto
CONF_TEXT_ITALIC = "text_italic"
CONF_TEXT_UNDERLINE = "text_underline"
CONF_TEXT_HEADING = "text_heading"
CONF_TEXT_AUTO_COLOR = "text_auto_color"  # màu dùng cho chế độ auto của «Màu chữ»: red | orange | yellow | green
TEXT_SIZE_OPTIONS = ("off", "small", "big", "auto")
TEXT_COLOR_OPTIONS = ("off", "auto", "red", "orange", "yellow", "green")
TEXT_TOGGLE_OPTIONS = ("off", "on", "auto")
TEXT_AUTO_COLOR_OPTIONS = ("red", "orange", "yellow", "green")
# khoá mặc định trên thiết bị -> (khoá trong style gửi app, các giá trị hợp lệ, trường tương ứng của dịch vụ send_message)
TEXT_STYLE_KEYS = {CONF_TEXT_SIZE: ("size", TEXT_SIZE_OPTIONS, "font_size"), CONF_TEXT_COLOR: ("color", TEXT_COLOR_OPTIONS, "text_color"),
                   CONF_TEXT_BOLD: ("bold", TEXT_TOGGLE_OPTIONS, "bold"), CONF_TEXT_ITALIC: ("italic", TEXT_TOGGLE_OPTIONS, "italic"),
                   CONF_TEXT_UNDERLINE: ("underline", TEXT_TOGGLE_OPTIONS, "underline"), CONF_TEXT_HEADING: ("heading", TEXT_TOGGLE_OPTIONS, "heading"),
                   CONF_TEXT_AUTO_COLOR: ("auto_color", TEXT_AUTO_COLOR_OPTIONS, "auto_color")}
AI_EMPHASIS = ("off", "red", "orange", "yellow", "green")
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
CONF_ECHO_GUARD = "echo_guard"          # chong vong: auto | on (chan mic) | duplex (song cong R1) | off
ECHO_MODES = ("auto", "on", "duplex", "off")
CONF_AUTO_VIDEO_DELAY = "auto_video_delay"   # giay cho truoc khi tu dong y (0 = ngay)
MAX_AUTO_VIDEO_DELAY = 120
CONF_AUTO_ANSWER = "auto_answer"              # tu nghe may cuoc goi 1-1 DEN tu nguoi trong danh sach
CONF_AUTO_ANSWER_DELAY = "auto_answer_delay"  # giay cho truoc khi tu nghe may (bo dem; 0 = ngay)
CONF_AUTO_ANSWER_FROM = "auto_answer_from"    # ID Zalo duoc tu nghe, cach nhau dau phay (trong = khong ai)
MAX_AUTO_ANSWER_DELAY = 120
CONF_AI_CALL = "ai_call"                      # AI nghe va tra loi bang giong noi trong cuoc goi DEN (STT -> tro ly -> TTS)
CONF_AI_CALL_GREETING = "ai_call_greeting"    # cau chao dau cuoc goi (trong = cau mac dinh)
CONF_CALL_VOLUME = "call_volume"   # % am luong loa luc dang goi (0 = giu nguyen am luong cua loa)
MAX_CALL_VOLUME = 100
STORAGE_VERSION = 1
NONE_LABEL = "Không"
TEST_SOURCE = "test"                       # camera «test»: app Zalo tự tạo hình kiểm tra (các ô màu + đồng hồ) thay vì đọc camera
TEST_LABEL = "Hình kiểm tra (test)"
MIC_URL_LABEL = "URL (ô Mic URL)"
