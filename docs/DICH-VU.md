# Danh mục dịch vụ Zalo Call

> **Tệp này được SINH TỰ ĐỘNG** từ `custom_components/zalo_call/services.yaml` bằng `zalo/zalo-pc-app/tools/gen_service_docs.py`; đừng sửa tay.

Mọi dịch vụ gọi bằng `action: zalo_call.<tên>` (Công cụ nhà phát triển → Hành động, hoặc trong automation). Ô `entry_id` có ở mọi dịch vụ (chọn tài khoản Zalo) và **chỉ cần khi bạn có nhiều tài khoản**, nên các ví dụ bỏ qua. Dịch vụ đánh dấu ⚠️ xoá hoặc đổi dữ liệu thật.

Có **365 dịch vụ**. Hướng dẫn các trường hợp dùng cuộc gọi, AI, cảnh báo và quy tắc: xem [README](../README.md).  

## Mục lục

- **Cuộc gọi, AI và cảnh báo** (15): [`make_call`](#make_call), [`alert_call`](#alert_call), [`answer_call`](#answer_call), [`reject_call`](#reject_call), [`end_call`](#end_call), [`say_in_call`](#say_in_call), [`take_over_call`](#take_over_call), [`accept_video`](#accept_video), [`upgrade_to_video`](#upgrade_to_video), [`start_call_video`](#start_call_video), [`stop_call_video`](#stop_call_video), [`start_call_mic`](#start_call_mic), [`stop_call_mic`](#stop_call_mic), [`set_default_devices`](#set_default_devices), [`get_default_devices`](#get_default_devices)
- **Quy tắc cho cuộc gọi đến và tin nhắn** (4): [`set_rule`](#set_rule), [`remove_rule`](#remove_rule), [`list_rules`](#list_rules), [`list_contacts`](#list_contacts)
- **Tin nhắn** (20): [`send_message`](#send_message), [`send_file`](#send_file), [`send_image`](#send_image), [`send_image_to_user`](#send_image_to_user), [`send_images_to_user`](#send_images_to_user), [`send_image_to_group`](#send_image_to_group), [`send_images_to_group`](#send_images_to_group), [`undo_message`](#undo_message), [`send_voice`](#send_voice), [`get_group_chat_history`](#get_group_chat_history), [`add_reaction`](#add_reaction), [`delete_message`](#delete_message), [`forward_message`](#forward_message), [`parse_link`](#parse_link), [`send_card`](#send_card), [`send_link`](#send_link), [`send_video`](#send_video), [`quote_message`](#quote_message), [`mark_seen`](#mark_seen), [`fetch_important`](#fetch_important)
- **Tài khoản và webhook** (10): [`get_logged_accounts`](#get_logged_accounts), [`get_account_details`](#get_account_details), [`get_account_webhooks`](#get_account_webhooks), [`get_account_webhook`](#get_account_webhook), [`set_account_webhook`](#set_account_webhook), [`delete_account_webhook`](#delete_account_webhook), [`get_proxies`](#get_proxies), [`add_proxy`](#add_proxy), [`remove_proxy`](#remove_proxy), [`get_login_qr`](#get_login_qr)
- **Hồ sơ và bạn bè** (21): [`find_user`](#find_user), [`get_user_info`](#get_user_info), [`send_friend_request`](#send_friend_request), [`accept_friend_request`](#accept_friend_request), [`block_user`](#block_user), [`unblock_user`](#unblock_user), [`get_all_friends`](#get_all_friends), [`get_sent_friend_requests`](#get_sent_friend_requests), [`undo_friend_request`](#undo_friend_request), [`remove_friend`](#remove_friend), [`change_friend_alias`](#change_friend_alias), [`remove_friend_alias`](#remove_friend_alias), [`get_all_groups`](#get_all_groups), [`update_profile`](#update_profile), [`update_settings`](#update_settings), [`block_view_feed`](#block_view_feed), [`change_account_avatar`](#change_account_avatar), [`get_avatar_list`](#get_avatar_list), [`last_online`](#last_online), [`reject_friend_request`](#reject_friend_request), [`get_settings`](#get_settings)
- **Nhóm** (22): [`create_group`](#create_group), [`get_group_info`](#get_group_info), [`add_user_to_group`](#add_user_to_group), [`remove_user_from_group`](#remove_user_from_group), [`change_group_name`](#change_group_name), [`change_group_avatar`](#change_group_avatar), [`add_group_deputy`](#add_group_deputy), [`remove_group_deputy`](#remove_group_deputy), [`change_group_owner`](#change_group_owner), [`disperse_group`](#disperse_group), [`enable_group_link`](#enable_group_link), [`disable_group_link`](#disable_group_link), [`join_group`](#join_group), [`leave_group`](#leave_group), [`create_note_group`](#create_note_group), [`edit_note_group`](#edit_note_group), [`get_list_board`](#get_list_board), [`create_poll`](#create_poll), [`get_poll_detail`](#get_poll_detail), [`lock_poll`](#lock_poll), [`get_group_link`](#get_group_link), [`vote_poll`](#vote_poll)
- **Sticker** (3): [`send_sticker`](#send_sticker), [`get_stickers`](#get_stickers), [`get_stickers_detail`](#get_stickers_detail)
- **Nhắc hẹn** (10): [`create_reminder`](#create_reminder), [`remove_reminder`](#remove_reminder), [`edit_reminder`](#edit_reminder), [`get_reminder`](#get_reminder), [`get_list_reminder`](#get_list_reminder), [`get_reminder_responses`](#get_reminder_responses), [`add_quick_message`](#add_quick_message), [`get_quick_message`](#get_quick_message), [`remove_quick_message`](#remove_quick_message), [`update_quick_message`](#update_quick_message)
- **Hội thoại** (15): [`set_mute`](#set_mute), [`set_pinned_conversation`](#set_pinned_conversation), [`get_unread_mark`](#get_unread_mark), [`add_unread_mark`](#add_unread_mark), [`remove_unread_mark`](#remove_unread_mark), [`delete_chat`](#delete_chat), [`get_archived_chat_list`](#get_archived_chat_list), [`get_auto_delete_chat`](#get_auto_delete_chat), [`update_auto_delete_chat`](#update_auto_delete_chat), [`get_hidden_conversations`](#get_hidden_conversations), [`set_hidden_conversations`](#set_hidden_conversations), [`update_hidden_convers_pin`](#update_hidden_convers_pin), [`reset_hidden_convers_pin`](#reset_hidden_convers_pin), [`get_mute`](#get_mute), [`get_pin_conversations`](#get_pin_conversations)
- **Nhãn và «đang nhập»** (3): [`get_labels`](#get_labels), [`send_typing_event`](#send_typing_event), [`update_label`](#update_label)
- **Phiên và xác thực (nâng cao)** (13): [`decrypt_gids`](#decrypt_gids), [`encrypt_gids`](#encrypt_gids), [`export_session`](#export_session), [`get_context`](#get_context), [`get_cookie`](#get_cookie), [`get_list_device`](#get_list_device), [`get_noised_ids`](#get_noised_ids), [`get_own_id`](#get_own_id), [`get_q_r`](#get_q_r), [`lost_focus`](#lost_focus), [`scan_u_r_l`](#scan_u_r_l), [`update_active_status`](#update_active_status), [`update_lang`](#update_lang)
- **Chat (nâng cao)** (26): [`get_block_sharing_conversations`](#get_block_sharing_conversations), [`get_conv_offline_messages`](#get_conv_offline_messages), [`get_direct_message_status`](#get_direct_message_status), [`get_last_seen`](#get_last_seen), [`get_last_seen_reaction`](#get_last_seen_reaction), [`get_recent_search_list`](#get_recent_search_list), [`get_suggested_conversations`](#get_suggested_conversations), [`get_translate_setting`](#get_translate_setting), [`mark_sub_tab_seen`](#mark_sub_tab_seen), [`preload_conversations`](#preload_conversations), [`renew_message_link`](#renew_message_link), [`send_bank_card`](#send_bank_card), [`send_delivered_event`](#send_delivered_event), [`send_report`](#send_report), [`send_seen_event`](#send_seen_event), [`set_pinned_conversations`](#set_pinned_conversations), [`translate_message`](#translate_message), [`translate_message_auto`](#translate_message_auto), [`translate_message_suggest`](#translate_message_suggest), [`undo`](#undo), [`undo_multi_message`](#undo_multi_message), [`update_archived_chat_list`](#update_archived_chat_list), [`update_block_sharing_conversation`](#update_block_sharing_conversation), [`update_pin_conversations`](#update_pin_conversations), [`update_recent_search`](#update_recent_search), [`update_translate_setting`](#update_translate_setting)
- **Nhóm (nâng cao)** (28): [`add_group_blocked_member`](#add_group_blocked_member), [`analyse_group`](#analyse_group), [`check_quota_community_member`](#check_quota_community_member), [`delete_group_invite_box`](#delete_group_invite_box), [`get_e2ee_group_list`](#get_e2ee_group_list), [`get_extra_group_info`](#get_extra_group_info), [`get_group_blocked_member`](#get_group_blocked_member), [`get_group_cloud_message_jump`](#get_group_cloud_message_jump), [`get_group_cloud_message_path`](#get_group_cloud_message_path), [`get_group_info_v2`](#get_group_info_v2), [`get_group_invite_box_info`](#get_group_invite_box_info), [`get_group_invite_box_list`](#get_group_invite_box_list), [`get_group_link_info`](#get_group_link_info), [`get_group_list_v3`](#get_group_list_v3), [`get_group_members_info`](#get_group_members_info), [`get_group_message_status`](#get_group_message_status), [`get_multi_group_cloud_messages`](#get_multi_group_cloud_messages), [`get_pending_group_members`](#get_pending_group_members), [`get_quota_community`](#get_quota_community), [`get_related_friend_group`](#get_related_friend_group), [`invite_user_to_groups`](#invite_user_to_groups), [`join_group_invite_box`](#join_group_invite_box), [`remove_group_blocked_member`](#remove_group_blocked_member), [`remove_group_topic`](#remove_group_topic), [`remove_user_from_groups`](#remove_user_from_groups), [`review_pending_member_request`](#review_pending_member_request), [`update_group_settings`](#update_group_settings), [`upgrade_group_to_community`](#upgrade_group_to_community)
- **Bạn bè (nâng cao)** (22): [`clear_unread_friend_requests`](#clear_unread_friend_requests), [`find_user_by_username`](#find_user_by_username), [`get_alias_list`](#get_alias_list), [`get_alias_list_v2`](#get_alias_list_v2), [`get_block_friends`](#get_block_friends), [`get_close_friends`](#get_close_friends), [`get_extra_friend_info`](#get_extra_friend_info), [`get_friend_board_list`](#get_friend_board_list), [`get_friend_onlines`](#get_friend_onlines), [`get_friend_recommendations`](#get_friend_recommendations), [`get_friend_request_status`](#get_friend_request_status), [`get_friends_active_p_c_web`](#get_friends_active_p_c_web), [`get_friends_emoji_status`](#get_friends_emoji_status), [`get_last_read_contact_tab`](#get_last_read_contact_tab), [`get_multi_user_q_r_codes`](#get_multi_user_q_r_codes), [`get_multi_users_by_phones`](#get_multi_users_by_phones), [`get_phonebook_v2`](#get_phonebook_v2), [`read_contact_tab`](#read_contact_tab), [`remove_friend_recommendation`](#remove_friend_recommendation), [`remove_friend_recommendation_v2`](#remove_friend_recommendation_v2), [`update_close_friend`](#update_close_friend), [`verify_friend`](#verify_friend)
- **Hồ sơ (nâng cao)** (16): [`delete_avatar`](#delete_avatar), [`disable_limit_search_phone_reminder`](#disable_limit_search_phone_reminder), [`fetch_account_info`](#fetch_account_info), [`get_avatar_url_profile`](#get_avatar_url_profile), [`get_emoji_status_config`](#get_emoji_status_config), [`get_enterprise_profiles`](#get_enterprise_profiles), [`get_full_avatar`](#get_full_avatar), [`get_mini_profile`](#get_mini_profile), [`get_profile_extra`](#get_profile_extra), [`get_profile_rank`](#get_profile_rank), [`get_profile_verification_status`](#get_profile_verification_status), [`push_profile_verification_message`](#push_profile_verification_message), [`register_trial_biz_account`](#register_trial_biz_account), [`reuse_avatar`](#reuse_avatar), [`update_profile_bio`](#update_profile_bio), [`update_profile_mode`](#update_profile_mode)
- **Đồng bộ (nâng cao)** (10): [`cancel_pull_mobile`](#cancel_pull_mobile), [`delete_mobile_msg_snapshot`](#delete_mobile_msg_snapshot), [`download_transfer_sync`](#download_transfer_sync), [`get_backup_msg_info`](#get_backup_msg_info), [`get_cross_db_info`](#get_cross_db_info), [`get_sync_data`](#get_sync_data), [`pull_mobile`](#pull_mobile), [`request_sync_from_phone`](#request_sync_from_phone), [`submit_sync_media_actions`](#submit_sync_media_actions), [`upload_backup_chunk`](#upload_backup_chunk)
- **Zalo Cloud** (16): [`ack_cloud_onboarding`](#ack_cloud_onboarding), [`get_cloud_download_urls`](#get_cloud_download_urls), [`get_cloud_info`](#get_cloud_info), [`get_cloud_settings`](#get_cloud_settings), [`get_cloud_upload_url`](#get_cloud_upload_url), [`get_cloud_viewer_key`](#get_cloud_viewer_key), [`get_family_profile`](#get_family_profile), [`get_family_usage`](#get_family_usage), [`get_family_viewer_key`](#get_family_viewer_key), [`get_usage_my_cloud`](#get_usage_my_cloud), [`get_usage_z_cloud`](#get_usage_z_cloud), [`migrate_cloud_recent`](#migrate_cloud_recent), [`reset_cloud_queue`](#reset_cloud_queue), [`submit_cloud_media_ext_info`](#submit_cloud_media_ext_info), [`submit_cloud_verify_action`](#submit_cloud_verify_action), [`verify_cloud_media`](#verify_cloud_media)
- **Cuộc gọi theo thư viện zca-js (nâng cao)** (30): [`add_user_group_call`](#add_user_group_call), [`answer_ack_voice_call`](#answer_ack_voice_call), [`answer_group_call`](#answer_group_call), [`answer_voice_call`](#answer_voice_call), [`broadcast_group_call_state`](#broadcast_group_call_state), [`cancel_group_call`](#cancel_group_call), [`cancel_voice_call`](#cancel_voice_call), [`create_controller`](#create_controller), [`create_rtc_session`](#create_rtc_session), [`end_group_call`](#end_group_call), [`end_voice_call`](#end_voice_call), [`finish_group_call`](#finish_group_call), [`get_group_call_state`](#get_group_call_state), [`hold_voice_call`](#hold_voice_call), [`join_group_call`](#join_group_call), [`log_end_voice_call`](#log_end_voice_call), [`notify_group_call`](#notify_group_call), [`ping_group_call`](#ping_group_call), [`request_audio_to_video_call`](#request_audio_to_video_call), [`request_group_call`](#request_group_call), [`request_share_screen_call`](#request_share_screen_call), [`request_voice_call`](#request_voice_call), [`ring_ring_group_call`](#ring_ring_group_call), [`ring_ring_voice_call`](#ring_ring_voice_call), [`send_request_group_call`](#send_request_group_call), [`send_request_voice_call`](#send_request_voice_call), [`send_voice_call`](#send_voice_call), [`share_screen_group_call`](#share_screen_group_call), [`unhold_voice_call`](#unhold_voice_call), [`update_call_media_state`](#update_call_media_state)
- **Phương tiện** (7): [`get_conversation_media`](#get_conversation_media), [`get_media_store_preview`](#get_media_store_preview), [`get_personal_media`](#get_personal_media), [`get_personal_media_preview`](#get_personal_media_preview), [`remove_conversation_media`](#remove_conversation_media), [`remove_personal_media`](#remove_personal_media), [`upload_attachment`](#upload_attachment)
- **Sticker (nâng cao)** (21): [`get_a_i_sticker_list`](#get_a_i_sticker_list), [`get_default_guggy_gifs`](#get_default_guggy_gifs), [`get_gif_categories`](#get_gif_categories), [`get_gif_dictionaries`](#get_gif_dictionaries), [`get_gifs_by_category`](#get_gifs_by_category), [`get_gifs_by_dictionary`](#get_gifs_by_dictionary), [`get_message_effect_by_id`](#get_message_effect_by_id), [`get_message_effects`](#get_message_effects), [`get_personalized_sticker_list`](#get_personalized_sticker_list), [`get_recommended_stickers`](#get_recommended_stickers), [`get_sticker_categories_v2`](#get_sticker_categories_v2), [`get_sticker_category_detail`](#get_sticker_category_detail), [`get_sticker_hello`](#get_sticker_hello), [`get_sticker_suggest_keywords`](#get_sticker_suggest_keywords), [`get_sticker_suggestion`](#get_sticker_suggestion), [`get_tenor_sticker_mapping`](#get_tenor_sticker_mapping), [`get_trending_gifs`](#get_trending_gifs), [`search_gifs`](#search_gifs), [`search_guggy_gifs`](#search_guggy_gifs), [`search_sticker`](#search_sticker), [`update_personalized_sticker_list`](#update_personalized_sticker_list)
- **Ghi chú, bình chọn, việc cần làm** (21): [`ack_ding_todo`](#ack_ding_todo), [`add_poll_options`](#add_poll_options), [`create_note`](#create_note), [`create_todo`](#create_todo), [`delete_todo`](#delete_todo), [`ding_todo`](#ding_todo), [`edit_note`](#edit_note), [`get_list_pin_topics`](#get_list_pin_topics), [`get_todo_detail`](#get_todo_detail), [`get_todo_list`](#get_todo_list), [`multi_unpin_board_topics`](#multi_unpin_board_topics), [`pin_board_topic`](#pin_board_topic), [`pin_friend_message`](#pin_friend_message), [`reorder_friend_board`](#reorder_friend_board), [`reorder_pin_topics`](#reorder_pin_topics), [`share_poll`](#share_poll), [`unpin_board_topic`](#unpin_board_topic), [`unpin_friend_messages`](#unpin_friend_messages), [`update_todo`](#update_todo), [`update_todo_status`](#update_todo_status), [`verify_todo`](#verify_todo)
- **Zalo Business (OA)** (30): [`add_conversation_label`](#add_conversation_label), [`block_o_a`](#block_o_a), [`convert_o_a_ids`](#convert_o_a_ids), [`create_auto_reply`](#create_auto_reply), [`create_bank_account`](#create_bank_account), [`create_catalog`](#create_catalog), [`create_product_catalog`](#create_product_catalog), [`delete_auto_reply`](#delete_auto_reply), [`delete_bank_account`](#delete_bank_account), [`delete_catalog`](#delete_catalog), [`delete_conversation_label`](#delete_conversation_label), [`delete_product_catalog`](#delete_product_catalog), [`delete_single_product`](#delete_single_product), [`get_auto_reply_list`](#get_auto_reply_list), [`get_biz_account`](#get_biz_account), [`get_catalog_list`](#get_catalog_list), [`get_list_bank`](#get_list_bank), [`get_list_bank_account`](#get_list_bank_account), [`get_o_a_profile`](#get_o_a_profile), [`get_product_catalog_list`](#get_product_catalog_list), [`get_product_detail`](#get_product_detail), [`register_catalog`](#register_catalog), [`reorder_conversation_labels`](#reorder_conversation_labels), [`unblock_o_a`](#unblock_o_a), [`update_auto_reply`](#update_auto_reply), [`update_bank_account`](#update_bank_account), [`update_catalog`](#update_catalog), [`update_conversation_label_item`](#update_conversation_label_item), [`update_product_catalog`](#update_product_catalog), [`upload_product_photo`](#upload_product_photo)
- **Khác** (2): [`voice_to_text`](#voice_to_text), [`set_contact_tags`](#set_contact_tags)

## Cuộc gọi, AI và cảnh báo

<a id="make_call"></a>
#### Gọi điện đi — `zalo_call.make_call`

Gọi thoại hoặc video cho một người hay nhóm Zalo. Có thể chỉ gọi, hoặc đọc một thông báo rồi cúp, hoặc cho AI nói chuyện. Muốn báo động (có người ngã, cháy...) thì dùng «Gọi cảnh báo».

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.make_call
data:
  thread_id: "6643404425553198601"  # bắt buộc - Người hoặc nhóm cần gọi
  type: "user"                      # tuỳ chọn - Gọi thoại hay gọi video
  peer_name: "..."                  # tuỳ chọn - Tên hiện trong nhật ký
  srtp: "sess"                      # tuỳ chọn - Cách mã hoá tiếng (nâng cao)
  extend_profile: "native"          # tuỳ chọn - Kiểu kết nối với Zalo (nâng cao)
  speaker: "media_player.vi_du"     # tuỳ chọn - Loa trong nhà
  volume: 0                         # tuỳ chọn - Âm lượng loa (%)
  mic: "camera.vi_du"               # tuỳ chọn - Mic trong nhà
  mic_url: "..."                    # tuỳ chọn - Mic từ địa chỉ mạng (nâng cao)
  camera: "camera.vi_du"            # tuỳ chọn - Camera trong nhà
  connect: ["mic", "speaker"]       # tuỳ chọn - Thiết bị nhà dùng khi người nhà nói trực tiếp
  connect_now: ["mic", "speaker"]   # tuỳ chọn - Thiết bị nhà dùng NGAY khi người nhận nghe máy
  message: "..."                    # tuỳ chọn - Nội dung đọc khi người nhận nghe máy
  repeat: 1                         # tuỳ chọn - Đọc mấy lần
  ai: false                         # tuỳ chọn - Cho AI nói chuyện
  hangup_after: true                # tuỳ chọn - Tự cúp máy khi xong
  greeting: "..."                   # tuỳ chọn - Câu AI chào đầu tiên
  handover_rule: "..."              # tuỳ chọn - AI chuyển cho người nhà khi...
  tts_engine: "tts.vi_du"           # tuỳ chọn - Giọng đọc riêng
  language: "..."                   # tuỳ chọn - Ngôn ngữ
  pipeline: "Chatgpt"               # tuỳ chọn - Trợ lý giọng nói (Assist)
  agent: "conversation.vi_du"       # tuỳ chọn - Trợ lý AI riêng (không bắt buộc)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Người hoặc nhóm cần gọi | có | Mã Zalo của người (hoặc nhóm). Xem danh sách bằng dịch vụ «Xem danh bạ Zalo». |
| `type` | Gọi thoại hay gọi video | không | Thoại, video hoặc nhóm. Bỏ trống = tự chọn: nếu có camera sẽ dùng (tích Camera ở ô «Thiết bị nhà dùng khi người nhà nói trực tiếp») thì gọi video, không thì gọi thoại. |
| `peer_name` | Tên hiện trong nhật ký | không | Tên người nhận hiện trong nhật ký cuộc gọi (bỏ trống = dùng mã). |
| `srtp` | Cách mã hoá tiếng (nâng cao) | không | Thường để trống: hệ thống tự chọn cách đã chạy tốt. |
| `extend_profile` | Kiểu kết nối với Zalo (nâng cao) | không | Thường để trống. |
| `speaker` | Loa trong nhà | không | Loa phát tiếng người bên kia. Với cuộc gọi có AI: chỉ bật khi người nhà nói trực tiếp. |
| `volume` | Âm lượng loa (%) | không | Đặt âm lượng khi bật loa, trả lại mức cũ khi cúp. Bỏ trống = giữ nguyên. |
| `mic` | Mic trong nhà | không | Camera hoặc vệ tinh Assist (loa R1, camera Imou/Dahua) có mic, để gửi tiếng trong nhà cho người bên kia. Với cuộc gọi có AI: chỉ bật khi người nhà nói trực tiếp. |
| `mic_url` | Mic từ địa chỉ mạng (nâng cao) | không | Địa chỉ rtsp/http của luồng tiếng, nếu mic không có trong danh sách. Thắng ô Mic. |
| `camera` | Camera trong nhà | không | Camera gửi hình cho người bên kia (cuộc gọi video). Với cuộc gọi có AI: chỉ bật khi người nhà nói trực tiếp. |
| `connect` | Thiết bị nhà dùng khi người nhà nói trực tiếp | không | Tích ô nào thì dùng thứ đó: tích 1 = dùng 1, tích 2 = dùng 2, tích 3 = dùng cả 3. Không tích gì = không dùng thiết bị nào (mặc định, người lạ không nghe hay thấy được trong nhà). Tích Camera = cuộc gọi VIDEO. «AI tự chọn» = AI quyết dùng mic và loa hay thêm cả camera, chỉ trong các ô đã tích. Chỉ dùng được thiết bị đã chọn ở các ô Loa, Mic, Camera bên dưới. Thiết bị chỉ bật khi người nhà nói trực tiếp, lúc AI còn đang giữ máy thì chưa bật. |
| `connect_now` | Thiết bị nhà dùng NGAY khi người nhận nghe máy | không | Tích ô nào thì thứ đó bật ngay khi người nhận nghe máy, không chờ người nhà nói trực tiếp (ví dụ tích Camera để người nhận thấy hình trong nhà ngay, còn Mic và Loa chỉ bật khi người nhà nói). Tích Camera = cuộc gọi VIDEO. Không tích gì = chưa bật gì (mặc định). Chỉ bật được thiết bị đã chọn ở các ô Loa, Mic, Camera. |
| `message` | Nội dung đọc khi người nhận nghe máy | không | Câu được đọc bằng giọng nói ngay khi nghe máy. Bỏ trống = không đọc gì. |
| `repeat` | Đọc mấy lần | không | Số lần đọc (1 đến 3). |
| `ai` | Cho AI nói chuyện | không | AI nghe người bên kia và trả lời bằng giọng nói, tới khi họ nói không cần gì nữa, cúp máy, im lặng quá lâu hoặc 10 phút. Cần chọn Trợ lý giọng nói (hoặc đã đặt quy tắc cho người này). |
| `hangup_after` | Tự cúp máy khi xong | không | Cúp máy sau khi đọc xong thông báo, và sau khi AI nói chuyện xong. Mặc định: bật. |
| `greeting` | Câu AI chào đầu tiên | không | AI nói câu này ngay khi người nhận nghe máy (chỉ khi cho AI nói chuyện mà không có nội dung thông báo). Bỏ trống = câu chào trong quy tắc, không có thì «Xin chào, tôi là trợ lý của gia đình. Bạn cần gì ạ?». |
| `handover_rule` | AI chuyển cho người nhà khi... | không | Thêm điều kiện riêng để AI chuyển cuộc gọi cho người nhà nói trực tiếp. Mặc định AI đã tự chuyển khi người gọi muốn gặp người trong nhà, có việc khẩn cấp hoặc AI không giúp được. Khi chuyển, cuộc gọi không bị cúp, thiết bị nhà bật theo ô «Thiết bị nhà dùng khi người nhà nói trực tiếp», và Home Assistant bắn sự kiện zalo_call_ai_handover. |
| `tts_engine` | Giọng đọc riêng | không | Chọn nếu muốn dùng giọng khác. Bỏ trống = giọng của Trợ lý giọng nói. |
| `language` | Ngôn ngữ | không | Ví dụ vi. Bỏ trống = theo Trợ lý giọng nói. |
| `pipeline` | Trợ lý giọng nói (Assist) | không | Bộ nghe - hiểu - nói của Home Assistant (Cài đặt, Trợ lý giọng nói). Khi cho AI nói chuyện, AI nghe người gọi, trả lời và đọc bằng giọng của bộ này. Bắt buộc chọn nếu cho AI nói chuyện (không tự dùng bộ ưu tiên vì nó có quyền điều khiển thiết bị trong nhà). |
| `agent` | Trợ lý AI riêng (không bắt buộc) | không | Chỉ chọn nếu muốn dùng một trợ lý AI khác với trợ lý trong Trợ lý giọng nói. Với người lạ, nên chọn trợ lý KHÔNG điều khiển được thiết bị trong nhà. |

**Các lựa chọn:**

- **Gọi thoại hay gọi video** (`type`)
  - `user`: gọi thoại 1-1
  - `video`: gọi video 1-1
  - `group`: gọi nhóm
- **Cách mã hoá tiếng (nâng cao)** (`srtp`)
  - `sess`: khoá mã hoá lấy từ mã phiên của cuộc gọi (mặc định, đã chạy thật với điện thoại)
  - `off`: không mã hoá tiếng (RTP trần)
  - `key`: khoá tự sinh (thử nghiệm)
- **Kiểu kết nối với Zalo (nâng cao)** (`extend_profile`)
  - `native`: giống ứng dụng Zalo trên Linux (mặc định, đã chạy thật với điện thoại)
  - `pc`: bộ cũ của app (newZrtc=0)
  - `zca`: bộ của thư viện zca-js
- **Thiết bị nhà dùng khi người nhà nói trực tiếp** (`connect`) - chọn được nhiều ô cùng lúc
  - `mic`: Mic: gửi tiếng trong nhà cho người gọi
  - `speaker`: Loa: phát tiếng người gọi ra loa trong nhà
  - `camera`: Camera: gửi hình trong nhà (tích ô này là cuộc gọi VIDEO; cuộc thoại được nâng lên video)
  - `ai`: AI tự chọn: AI quyết dùng mic + loa hay thêm camera, chỉ trong các ô đã tích (không ô nào thì trong cả ba; AI không chọn thì chỉ mic + loa)
- **Thiết bị nhà dùng NGAY khi người nhận nghe máy** (`connect_now`) - chọn được nhiều ô cùng lúc
  - `mic`: bật mic ngay khi người nhận nghe máy
  - `speaker`: bật loa ngay khi người nhận nghe máy
  - `camera`: bật camera ngay khi người nhận nghe máy (và là cuộc gọi VIDEO)

---

<a id="alert_call"></a>
#### Gọi cảnh báo — `zalo_call.alert_call`

Gọi để BÁO ĐỘNG: người nhận nghe máy, AI đọc nội dung cảnh báo (không hỏi gì), rồi làm theo ô «Đọc cảnh báo xong thì». Báo người ngã, có trộm: nên nối thiết bị nhà để người nhận xem hiện trường. Báo mất điện, rò nước: đọc xong cúp máy. Đọc xong, Home Assistant bắn sự kiện zalo_call_alert_done để automation biết đúng lúc đó.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.alert_call
data:
  thread_id: "6643404425553198601"  # bắt buộc - Người cần báo
  message: "..."                    # bắt buộc - Nội dung cảnh báo
  type: "user"                      # tuỳ chọn - Gọi thoại hay gọi video
  after: "hangup"                   # tuỳ chọn - Đọc cảnh báo xong thì
  pipeline: "Chatgpt"               # tuỳ chọn - Trợ lý giọng nói (để chọn giọng đọc)
  speaker: "media_player.vi_du"     # tuỳ chọn - Loa trong nhà
  mic: "camera.vi_du"               # tuỳ chọn - Mic trong nhà
  mic_url: "..."                    # tuỳ chọn - Mic từ địa chỉ mạng (nâng cao)
  camera: "camera.vi_du"            # tuỳ chọn - Camera trong nhà
  connect: ["mic", "speaker"]       # tuỳ chọn - Thiết bị nhà dùng ngay sau cảnh báo
  volume: 0                         # tuỳ chọn - Âm lượng loa (%)
  repeat: 1                         # tuỳ chọn - Đọc mấy lần
  tts_engine: "tts.vi_du"           # tuỳ chọn - Giọng đọc riêng
  language: "..."                   # tuỳ chọn - Ngôn ngữ
  peer_name: "..."                  # tuỳ chọn - Tên hiện trong nhật ký
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Người cần báo | có | Mã Zalo của người nhận cảnh báo. Xem danh sách bằng dịch vụ «Xem danh bạ Zalo». |
| `message` | Nội dung cảnh báo | có | Câu được đọc ngay khi người nhận nghe máy. |
| `type` | Gọi thoại hay gọi video | không | Bỏ trống = tự chọn: có camera sẽ dùng (mặc định cảnh báo dùng tất cả thiết bị đã cài, gồm camera) thì gọi video, không thì gọi thoại. |
| `after` | Đọc cảnh báo xong thì | không | Cúp máy: hợp báo mất điện, rò nước. Nối thiết bị nhà: hợp báo người ngã, có trộm. Giữ máy: người nhận hoặc automation tự cúp (dịch vụ «Kết thúc cuộc gọi»). Bỏ trống = tự chọn: có thiết bị để nối thì nối, không thì cúp. |
| `pipeline` | Trợ lý giọng nói (để chọn giọng đọc) | không | Bỏ trống = theo quy tắc của người này; không có thì giọng đọc mặc định của Home Assistant. |
| `speaker` | Loa trong nhà | không | Loa phát tiếng người nhận sau khi đọc xong. Bỏ trống = theo quy tắc của người này. |
| `mic` | Mic trong nhà | không | Mic gửi tiếng trong nhà cho người nhận sau khi đọc xong. Bỏ trống = theo quy tắc. |
| `mic_url` | Mic từ địa chỉ mạng (nâng cao) | không | Địa chỉ rtsp/http của luồng tiếng, nếu mic không có trong danh sách. Thắng ô Mic. |
| `camera` | Camera trong nhà | không | Camera gửi hình cho người nhận sau khi đọc xong. Bỏ trống = theo quy tắc. |
| `connect` | Thiết bị nhà dùng ngay sau cảnh báo | không | Tích ô nào thì dùng thứ đó (tích 1 = dùng 1, tích 2 = dùng 2, tích 3 = cả 3). Tích Camera = cuộc gọi VIDEO. Bỏ trống = dùng TẤT CẢ thiết bị đã cài, kể cả camera, vì báo động thì người nhận phải thấy hiện trường. Muốn chỉ đọc rồi cúp thì chọn Cúp máy ở ô «Đọc cảnh báo xong thì». |
| `volume` | Âm lượng loa (%) | không | Đặt âm lượng khi bật loa, trả lại mức cũ khi cúp. Bỏ trống = giữ nguyên. |
| `repeat` | Đọc mấy lần | không | Số lần đọc (1 đến 3). |
| `tts_engine` | Giọng đọc riêng | không | Chọn nếu muốn dùng giọng khác. Bỏ trống = giọng của Trợ lý giọng nói. |
| `language` | Ngôn ngữ | không | Ví dụ vi. Bỏ trống = theo Trợ lý giọng nói. |
| `peer_name` | Tên hiện trong nhật ký | không | Tên người nhận hiện trong nhật ký cuộc gọi (bỏ trống = dùng mã). |

**Các lựa chọn:**

- **Gọi thoại hay gọi video** (`type`)
  - `user`: gọi thoại
  - `video`: gọi video
- **Đọc cảnh báo xong thì** (`after`)
  - `hangup`: cúp máy ngay sau khi đọc xong (hợp báo mất điện, rò nước)
  - `connect`: nối thiết bị nhà đã cài (hợp báo người ngã, có trộm)
  - `wait`: giữ máy: người nhận hoặc automation tự cúp bằng dịch vụ «Kết thúc cuộc gọi»
- **Thiết bị nhà dùng ngay sau cảnh báo** (`connect`) - chọn được nhiều ô cùng lúc
  - `mic`: Mic: gửi tiếng trong nhà cho người gọi
  - `speaker`: Loa: phát tiếng người gọi ra loa trong nhà
  - `camera`: Camera: gửi hình trong nhà (tích ô này là cuộc gọi VIDEO; cuộc thoại được nâng lên video)
  - `ai`: AI tự chọn: AI quyết dùng mic + loa hay thêm camera, chỉ trong các ô đã tích (không ô nào thì trong cả ba; AI không chọn thì chỉ mic + loa)

---

<a id="answer_call"></a>
#### Nghe máy — `zalo_call.answer_call`

Nghe một cuộc gọi đang đổ chuông. Có thể kèm thông báo hoặc cho AI nói chuyện, giống «Gọi điện đi».

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.answer_call
data:
  call_id: "..."                   # tuỳ chọn - Mã cuộc gọi
  speaker: "media_player.vi_du"    # tuỳ chọn - Loa trong nhà
  volume: 0                        # tuỳ chọn - Âm lượng loa (%)
  mic: "camera.vi_du"              # tuỳ chọn - Mic trong nhà
  mic_url: "..."                   # tuỳ chọn - Mic từ địa chỉ mạng (nâng cao)
  camera: "camera.vi_du"           # tuỳ chọn - Camera trong nhà
  connect: ["mic", "speaker"]      # tuỳ chọn - Thiết bị nhà dùng khi người nhà nói trực tiếp
  connect_now: ["mic", "speaker"]  # tuỳ chọn - Thiết bị nhà dùng NGAY khi người nhận nghe máy
  message: "..."                   # tuỳ chọn - Nội dung đọc khi người nhận nghe máy
  repeat: 1                        # tuỳ chọn - Đọc mấy lần
  ai: false                        # tuỳ chọn - Cho AI nói chuyện
  hangup_after: true               # tuỳ chọn - Tự cúp máy khi xong
  greeting: "..."                  # tuỳ chọn - Câu AI chào đầu tiên
  handover_rule: "..."             # tuỳ chọn - AI chuyển cho người nhà khi...
  tts_engine: "tts.vi_du"          # tuỳ chọn - Giọng đọc riêng
  language: "..."                  # tuỳ chọn - Ngôn ngữ
  pipeline: "Chatgpt"              # tuỳ chọn - Trợ lý giọng nói (Assist)
  agent: "conversation.vi_du"      # tuỳ chọn - Trợ lý AI riêng (không bắt buộc)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để nghe cuộc gọi đến hiện tại. |
| `speaker` | Loa trong nhà | không | Loa phát tiếng người bên kia. Với cuộc gọi có AI: chỉ bật khi người nhà nói trực tiếp. |
| `volume` | Âm lượng loa (%) | không | Đặt âm lượng khi bật loa, trả lại mức cũ khi cúp. Bỏ trống = giữ nguyên. |
| `mic` | Mic trong nhà | không | Camera hoặc vệ tinh Assist (loa R1, camera Imou/Dahua) có mic, để gửi tiếng trong nhà cho người bên kia. Với cuộc gọi có AI: chỉ bật khi người nhà nói trực tiếp. |
| `mic_url` | Mic từ địa chỉ mạng (nâng cao) | không | Địa chỉ rtsp/http của luồng tiếng, nếu mic không có trong danh sách. Thắng ô Mic. |
| `camera` | Camera trong nhà | không | Camera gửi hình cho người bên kia (cuộc gọi video). Với cuộc gọi có AI: chỉ bật khi người nhà nói trực tiếp. |
| `connect` | Thiết bị nhà dùng khi người nhà nói trực tiếp | không | Tích ô nào thì dùng thứ đó: tích 1 = dùng 1, tích 2 = dùng 2, tích 3 = dùng cả 3. Không tích gì = không dùng thiết bị nào (mặc định, người lạ không nghe hay thấy được trong nhà). Tích Camera = cuộc gọi VIDEO. «AI tự chọn» = AI quyết dùng mic và loa hay thêm cả camera, chỉ trong các ô đã tích. Chỉ dùng được thiết bị đã chọn ở các ô Loa, Mic, Camera bên dưới. Thiết bị chỉ bật khi người nhà nói trực tiếp, lúc AI còn đang giữ máy thì chưa bật. |
| `connect_now` | Thiết bị nhà dùng NGAY khi người nhận nghe máy | không | Tích ô nào thì thứ đó bật ngay khi người nhận nghe máy, không chờ người nhà nói trực tiếp (ví dụ tích Camera để người nhận thấy hình trong nhà ngay, còn Mic và Loa chỉ bật khi người nhà nói). Tích Camera = cuộc gọi VIDEO. Không tích gì = chưa bật gì (mặc định). Chỉ bật được thiết bị đã chọn ở các ô Loa, Mic, Camera. |
| `message` | Nội dung đọc khi người nhận nghe máy | không | Câu được đọc bằng giọng nói ngay khi nghe máy. Bỏ trống = không đọc gì. |
| `repeat` | Đọc mấy lần | không | Số lần đọc (1 đến 3). |
| `ai` | Cho AI nói chuyện | không | AI nghe người bên kia và trả lời bằng giọng nói, tới khi họ nói không cần gì nữa, cúp máy, im lặng quá lâu hoặc 10 phút. Cần chọn Trợ lý giọng nói (hoặc đã đặt quy tắc cho người này). |
| `hangup_after` | Tự cúp máy khi xong | không | Cúp máy sau khi đọc xong thông báo, và sau khi AI nói chuyện xong. Mặc định: bật. |
| `greeting` | Câu AI chào đầu tiên | không | AI nói câu này ngay khi người nhận nghe máy (chỉ khi cho AI nói chuyện mà không có nội dung thông báo). Bỏ trống = câu chào trong quy tắc, không có thì «Xin chào, tôi là trợ lý của gia đình. Bạn cần gì ạ?». |
| `handover_rule` | AI chuyển cho người nhà khi... | không | Thêm điều kiện riêng để AI chuyển cuộc gọi cho người nhà nói trực tiếp. Mặc định AI đã tự chuyển khi người gọi muốn gặp người trong nhà, có việc khẩn cấp hoặc AI không giúp được. Khi chuyển, cuộc gọi không bị cúp, thiết bị nhà bật theo ô «Thiết bị nhà dùng khi người nhà nói trực tiếp», và Home Assistant bắn sự kiện zalo_call_ai_handover. |
| `tts_engine` | Giọng đọc riêng | không | Chọn nếu muốn dùng giọng khác. Bỏ trống = giọng của Trợ lý giọng nói. |
| `language` | Ngôn ngữ | không | Ví dụ vi. Bỏ trống = theo Trợ lý giọng nói. |
| `pipeline` | Trợ lý giọng nói (Assist) | không | Bộ nghe - hiểu - nói của Home Assistant (Cài đặt, Trợ lý giọng nói). Khi cho AI nói chuyện, AI nghe người gọi, trả lời và đọc bằng giọng của bộ này. Bắt buộc chọn nếu cho AI nói chuyện (không tự dùng bộ ưu tiên vì nó có quyền điều khiển thiết bị trong nhà). |
| `agent` | Trợ lý AI riêng (không bắt buộc) | không | Chỉ chọn nếu muốn dùng một trợ lý AI khác với trợ lý trong Trợ lý giọng nói. Với người lạ, nên chọn trợ lý KHÔNG điều khiển được thiết bị trong nhà. |

**Các lựa chọn:**

- **Thiết bị nhà dùng khi người nhà nói trực tiếp** (`connect`) - chọn được nhiều ô cùng lúc
  - `mic`: Mic: gửi tiếng trong nhà cho người gọi
  - `speaker`: Loa: phát tiếng người gọi ra loa trong nhà
  - `camera`: Camera: gửi hình trong nhà (tích ô này là cuộc gọi VIDEO; cuộc thoại được nâng lên video)
  - `ai`: AI tự chọn: AI quyết dùng mic + loa hay thêm camera, chỉ trong các ô đã tích (không ô nào thì trong cả ba; AI không chọn thì chỉ mic + loa)
- **Thiết bị nhà dùng NGAY khi người nhận nghe máy** (`connect_now`) - chọn được nhiều ô cùng lúc
  - `mic`: bật mic ngay khi người nhận nghe máy
  - `speaker`: bật loa ngay khi người nhận nghe máy
  - `camera`: bật camera ngay khi người nhận nghe máy (và là cuộc gọi VIDEO)

---

<a id="reject_call"></a>
#### Từ chối cuộc gọi đến — `zalo_call.reject_call`

Từ chối cuộc gọi đang đổ chuông.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.reject_call
data:
  call_id: "..."  # tuỳ chọn - Mã cuộc gọi
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để từ chối cuộc gọi đến hiện tại. |

---

<a id="end_call"></a>
#### Kết thúc cuộc gọi — `zalo_call.end_call`

Kết thúc (hoặc huỷ khi còn đổ chuông) cuộc gọi đang có.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.end_call
data:
  call_id: "..."  # tuỳ chọn - Mã cuộc gọi
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để kết thúc cuộc gọi gần nhất. |

---

<a id="say_in_call"></a>
#### Đọc lên cuộc gọi (TTS) — `zalo_call.say_in_call`

Đọc một câu bằng TTS của HA lên cuộc gọi đang nói.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.say_in_call
data:
  message: "..."           # bắt buộc - Nội dung
  call_id: "..."           # tuỳ chọn - Mã cuộc gọi
  tts_engine: "tts.vi_du"  # tuỳ chọn - Giọng đọc (TTS)
  language: "..."          # tuỳ chọn - Ngôn ngữ
  wait: true               # tuỳ chọn - Chờ đọc xong
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `message` | Nội dung | có | Câu cần đọc. |
| `call_id` | Mã cuộc gọi | không | Bỏ trống = cuộc gọi đang nói hiện tại. |
| `tts_engine` | Giọng đọc (TTS) | không | Thực thể tts.*; bỏ trống = mặc định của HA. |
| `language` | Ngôn ngữ | không | Ví dụ vi. |
| `wait` | Chờ đọc xong | không | Chờ đọc xong mới trả về. |

---

<a id="take_over_call"></a>
#### Người nhà nói trực tiếp (dừng AI) — `zalo_call.take_over_call`

Dừng AI đang giữ cuộc gọi và bật thiết bị nhà để người trong nhà nói chuyện trực tiếp với người gọi.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.take_over_call
data:
  call_id: "..."  # tuỳ chọn - Mã cuộc gọi
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống = cuộc gọi đang nói hiện tại. |

---

<a id="accept_video"></a>
#### Đồng ý chuyển sang video — `zalo_call.accept_video`

Người đang gọi thoại xin chuyển sang video, bạn đồng ý. Chọn Camera để gửi hình trong nhà; không chọn thì chỉ đồng ý (người gọi thấy mình, nhưng không thấy hình trong nhà). Chỉ dùng được khi cuộc gọi đang nói.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.accept_video
data:
  call_id: "..."          # tuỳ chọn - Mã cuộc gọi
  camera: "camera.vi_du"  # tuỳ chọn - Camera
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống = cuộc gọi đang nói hiện tại. |
| `camera` | Camera | không | Camera gửi hình. |

---

<a id="upgrade_to_video"></a>
#### Chuyển cuộc gọi thoại sang video — `zalo_call.upgrade_to_video`

Khi đang gọi thoại, xin bên kia chuyển sang video rồi phát camera đã chọn (hoặc camera mặc định).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.upgrade_to_video
data:
  call_id: "..."          # tuỳ chọn - Mã cuộc gọi
  camera: "camera.vi_du"  # tuỳ chọn - Camera
  camera_url: "..."       # tuỳ chọn - Camera từ URL
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để dùng cuộc gọi đang diễn ra. |
| `camera` | Camera | không | Camera HA phát hình. Bỏ trống = camera mặc định. |
| `camera_url` | Camera từ URL | không | rtsp/rtsps/http/https/rtmp (thắng ô Camera). |

---

<a id="start_call_video"></a>
#### Bật hình trong cuộc gọi — `zalo_call.start_call_video`

Phát hình camera lên cuộc gọi đang diễn ra (không xin chuyển loại cuộc gọi).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.start_call_video
data:
  call_id: "..."          # tuỳ chọn - Mã cuộc gọi
  camera: "camera.vi_du"  # tuỳ chọn - Camera
  camera_url: "..."       # tuỳ chọn - Camera từ URL
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để dùng cuộc gọi đang diễn ra. |
| `camera` | Camera | không | Camera HA phát hình. Bỏ trống = camera mặc định. |
| `camera_url` | Camera từ URL | không | rtsp/rtsps/http/https/rtmp (thắng ô Camera). |

---

<a id="stop_call_video"></a>
#### Tắt hình trong cuộc gọi — `zalo_call.stop_call_video`

Dừng phát hình camera lên cuộc gọi đang diễn ra.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.stop_call_video
data:
  call_id: "..."  # tuỳ chọn - Mã cuộc gọi
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để dùng cuộc gọi đang diễn ra. |

---

<a id="start_call_mic"></a>
#### Bật mic trong cuộc gọi — `zalo_call.start_call_mic`

Phát tiếng từ camera, vệ tinh Assist (camera Imou/Dahua, loa R1) hoặc URL lên cuộc gọi đang diễn ra.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.start_call_mic
data:
  call_id: "..."       # tuỳ chọn - Mã cuộc gọi
  mic: "camera.vi_du"  # tuỳ chọn - Mic
  mic_url: "..."       # tuỳ chọn - Mic từ URL
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để dùng cuộc gọi đang diễn ra. |
| `mic` | Mic | không | Camera hoặc vệ tinh Assist. Bỏ trống = mic mặc định. |
| `mic_url` | Mic từ URL | không | rtsp/rtsps/http/https/rtmp, hoặc luồng PCM của loa R1 (thắng ô Mic). |

---

<a id="stop_call_mic"></a>
#### Tắt mic trong cuộc gọi — `zalo_call.stop_call_mic`

Dừng phát tiếng lên cuộc gọi đang diễn ra.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.stop_call_mic
data:
  call_id: "..."  # tuỳ chọn - Mã cuộc gọi
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để dùng cuộc gọi đang diễn ra. |

---

<a id="set_default_devices"></a>
#### Đặt thiết bị mặc định — `zalo_call.set_default_devices`

Đặt loa, mic, camera và chế độ tự động mặc định (giống các thực thể trên thiết bị Zalo Call). Trường nào bỏ trống thì giữ nguyên; để rỗng thì bỏ thiết bị đó.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.set_default_devices
data:
  speaker: "media_player.vi_du"  # tuỳ chọn - Loa mặc định
  mic: "camera.vi_du"            # tuỳ chọn - Mic mặc định
  mic_url: "..."                 # tuỳ chọn - Mic mặc định từ URL
  camera: "camera.vi_du"         # tuỳ chọn - Camera mặc định
  auto_mic: false                # tuỳ chọn - Tự phát mic khi nghe máy
  auto_video: false              # tuỳ chọn - Tự đồng ý khi bên kia xin gọi video (mọi người)
  video_consent: false           # tuỳ chọn - Cho phép đồng ý chuyển sang video (công tắc tổng)
  echo_guard: "auto"             # tuỳ chọn - Chống vọng
  auto_video_delay: 0            # tuỳ chọn - Chờ trước khi tự đồng ý (giây)
  call_volume: 0                 # tuỳ chọn - Âm lượng cuộc gọi mặc định
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `speaker` | Loa mặc định | không | Loa (media_player) phát tiếng bên kia. |
| `mic` | Mic mặc định | không | Camera hoặc vệ tinh Assist (camera Imou/Dahua, loa R1) lấy tiếng. |
| `mic_url` | Mic mặc định từ URL | không | rtsp/rtsps/http/https/rtmp, hoặc luồng PCM của loa R1 (thắng ô Mic). |
| `camera` | Camera mặc định | không | Camera HA phát hình lên cuộc gọi video. |
| `auto_mic` | Tự phát mic khi nghe máy | không | Bật thì tự phát mic mặc định ngay khi cuộc gọi được nghe máy. |
| `auto_video` | Tự đồng ý khi bên kia xin gọi video (mọi người) | không | Bật thì khi BẤT KỲ AI xin chuyển sang video app cũng tự đồng ý và phát camera mặc định, không xét quy tắc từng người. Nên TẮT và dùng công tắc «Cho phép đồng ý chuyển sang video» cùng quy tắc từng người (video_request) để chỉ người được phép mới tự đồng ý. |
| `video_consent` | Cho phép đồng ý chuyển sang video (công tắc tổng) | không | Công tắc tổng, mặc định TẮT. Bật thì quy tắc video_request (accept, accept_camera) của từng người/nhóm mới được tự đồng ý khi họ xin chuyển sang video; tắt thì mọi người chỉ bị báo. Cũng là công tắc «Cho phép đồng ý chuyển sang video» trên thiết bị Zalo Call. |
| `echo_guard` | Chống vọng | không | auto = chỉ chặn mic khi mic và loa là cùng một thiết bị (ví dụ R1); on = luôn chặn mic khi loa đang phát tiếng bên kia; duplex = song công, nói chen được (loa R1 dùng khử vọng của nó); off = tắt. |
| `auto_video_delay` | Chờ trước khi tự đồng ý (giây) | không | Số giây chờ rồi mới tự đồng ý lời xin chuyển sang video (0 = đồng ý ngay; chỉ áp dụng khi cuộc gọi còn đang nói). |
| `call_volume` | Âm lượng cuộc gọi mặc định | không | 1-100 % — âm lượng loa đặt khi nghe máy rồi trả lại khi cuộc gọi kết thúc; 0 = giữ nguyên âm lượng loa. |

**Các lựa chọn:**

- **Chống vọng** (`echo_guard`)
  - `auto`: chỉ chặn mic khi mic và loa là cùng một thiết bị (ví dụ loa R1)
  - `on`: luôn chặn mic khi loa đang phát tiếng bên kia
  - `duplex`: song công: nói chen được (loa R1 dùng bộ khử vọng riêng)
  - `off`: tắt chống vọng

---

<a id="get_default_devices"></a>
#### Xem mic/loa/camera mặc định — `zalo_call.get_default_devices`

Trả về cài đặt thiết bị mặc định hiện tại (đặt bằng set_default_devices).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_default_devices
```

---

## Quy tắc cho cuộc gọi đến và tin nhắn

<a id="set_rule"></a>
#### Đặt quy tắc cho cuộc gọi đến và tin nhắn — `zalo_call.set_rule`

Quy định hệ thống làm gì khi có người gọi hoặc nhắn đến. Chưa có quy tắc cho người đó thì hệ thống KHÔNG làm gì (chỉ đổ chuông, không trả lời tin nhắn). Quy tắc cho một người hoặc nhóm cụ thể được ưu tiên hơn quy tắc chung. Ô nào không điền thì giữ nguyên như cũ; quy tắc mới mặc định TẮT hết và không dùng thiết bị nhà.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.set_rule
data:
  scope: "thread"                    # bắt buộc - Áp dụng cho
  thread_id: "6643404425553198601"   # tuỳ chọn - Mã Zalo của người hoặc nhóm
  tag: "gia đình"                    # tuỳ chọn - Thẻ
  name: "..."                        # tuỳ chọn - Tên gọi (để bạn nhớ)
  answer: false                      # tuỳ chọn - Tự nghe máy
  answer_delay: 3                    # tuỳ chọn - Nghe máy sau (giây)
  call_types: ["voice", "video"]     # tuỳ chọn - Nghe loại cuộc gọi nào
  ai: false                          # tuỳ chọn - Cho AI nói chuyện khi nghe máy
  pipeline: "Chatgpt"                # tuỳ chọn - Trợ lý giọng nói (Assist)
  agent: "conversation.vi_du"        # tuỳ chọn - Trợ lý AI riêng (không bắt buộc)
  greeting: "..."                    # tuỳ chọn - Câu AI chào khi nghe máy
  handover_rule: "..."               # tuỳ chọn - AI chuyển cho người nhà khi...
  trusted: false                     # tuỳ chọn - Người tin cậy
  reply_ai: false                    # tuỳ chọn - AI trả lời tin nhắn
  voice_text: false                  # tuỳ chọn - Chuyển tin thoại thành chữ
  reply_trigger: "..."               # tuỳ chọn - Từ khóa gọi AI trong nhóm
  reply_senders: "..."               # tuỳ chọn - Người được gọi AI trong nhóm
  reply_quote: false                 # tuỳ chọn - Trả lời kèm trích dẫn tin gốc
  reply_prefix: "..."                # tuỳ chọn - Tiền tố câu trả lời
  announce: false                    # tuỳ chọn - Báo ra loa khi có cuộc gọi đến
  announce_to: "media_player.vi_du"  # tuỳ chọn - Loa dùng để báo
  announce_text: "..."               # tuỳ chọn - Câu báo ra loa
  announce_volume: 0                 # tuỳ chọn - Âm lượng lúc báo (%)
  announce_repeat: 0                 # tuỳ chọn - Báo lại sau mỗi (giây)
  connect_now: ["mic", "speaker"]    # tuỳ chọn - Thiết bị nhà dùng NGAY khi người nhận nghe máy
  video_request: "ask"               # tuỳ chọn - Khi người gọi xin chuyển sang video
  connect: ["mic", "speaker"]        # tuỳ chọn - Thiết bị nhà dùng khi người nhà nói trực tiếp
  speaker: "media_player.vi_du"      # tuỳ chọn - Loa trong nhà
  mic: "camera.vi_du"                # tuỳ chọn - Mic trong nhà
  mic_url: "..."                     # tuỳ chọn - Mic từ địa chỉ mạng (nâng cao)
  camera: "camera.vi_du"             # tuỳ chọn - Camera trong nhà
  volume: 0                          # tuỳ chọn - Âm lượng loa (%)
  echo_guard: "auto"                 # tuỳ chọn - Chống vọng âm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `scope` | Áp dụng cho | có | Chọn đối tượng của quy tắc. «Một người hoặc một nhóm cụ thể» thì điền thêm Mã Zalo bên dưới. |
| `thread_id` | Mã Zalo của người hoặc nhóm | không | Chỉ cần khi chọn «Một người hoặc một nhóm cụ thể». Xem danh sách bằng dịch vụ «Xem danh bạ Zalo». |
| `tag` | Thẻ | không | Chỉ cần khi chọn «Mọi người mang một thẻ». Gắn thẻ cho người bằng dịch vụ «Gắn thẻ và ghi chú cho người». |
| `name` | Tên gọi (để bạn nhớ) | không | Tên hiển thị trong các thông báo, ví dụ «Con trai». |
| `answer` | Tự nghe máy | không | Cuộc gọi 1-1 đến từ người thuộc quy tắc này sẽ tự được nghe sau thời gian chờ. |
| `answer_delay` | Nghe máy sau (giây) | không | Từ 0 đến 120 giây. Người gọi cúp trước khi hết giờ thì không nghe. |
| `call_types` | Nghe loại cuộc gọi nào | không | voice = thoại, video = video, hoặc cả hai. |
| `ai` | Cho AI nói chuyện khi nghe máy | không | Sau khi nghe máy, AI nghe và trả lời bằng giọng nói. Cần chọn Trợ lý giọng nói hoặc Trợ lý AI riêng. |
| `pipeline` | Trợ lý giọng nói (Assist) | không | Bộ nghe - hiểu - nói của Home Assistant (Cài đặt, Trợ lý giọng nói). Khi cho AI nói chuyện, AI nghe người gọi, trả lời và đọc bằng giọng của bộ này. Bắt buộc chọn nếu cho AI nói chuyện (không tự dùng bộ ưu tiên vì nó có quyền điều khiển thiết bị trong nhà). |
| `agent` | Trợ lý AI riêng (không bắt buộc) | không | Chỉ chọn nếu muốn dùng một trợ lý AI khác với trợ lý trong Trợ lý giọng nói. Với người lạ, nên chọn trợ lý KHÔNG điều khiển được thiết bị trong nhà. |
| `greeting` | Câu AI chào khi nghe máy | không | Bỏ trống = «Xin chào, tôi là trợ lý của gia đình. Bạn cần gì ạ?». |
| `handover_rule` | AI chuyển cho người nhà khi... | không | Thêm điều kiện riêng để AI chuyển cuộc gọi cho người nhà nói trực tiếp. Mặc định AI đã tự chuyển khi người gọi muốn gặp người trong nhà, có việc khẩn cấp hoặc AI không giúp được. Khi chuyển, cuộc gọi không bị cúp, thiết bị nhà bật theo ô «Thiết bị nhà dùng khi người nhà nói trực tiếp», và Home Assistant bắn sự kiện zalo_call_ai_handover. |
| `trusted` | Người tin cậy | không | Tin cậy thì AI nói chuyện bình thường. Không tin cậy (mặc định) thì AI được dặn không tiết lộ thông tin gia đình và không điều khiển thiết bị. |
| `reply_ai` | AI trả lời tin nhắn | không | AI trả lời tin chữ (và tin thoại nếu bật chuyển tin thoại thành chữ) của người hoặc nhóm này. Cần chọn Trợ lý giọng nói hoặc Trợ lý AI riêng. |
| `voice_text` | Chuyển tin thoại thành chữ | không | Tin thoại 1-1 được Zalo chuyển thành chữ, và Home Assistant bắn sự kiện zalo_call_voice_text. |
| `reply_trigger` | Từ khóa gọi AI trong nhóm | không | Chỉ áp cho NHÓM. Tin có từ này (không phân biệt hoa thường, ví dụ `@Bot`) mới được AI trả lời; từ khóa được bỏ khỏi câu hỏi. Để trống = AI trả lời mọi tin của nhóm. |
| `reply_senders` | Người được gọi AI trong nhóm | không | Chỉ áp cho NHÓM. Mã Zalo (threadID) của những người được phép gọi AI, cách nhau dấu phẩy. Để trống = mọi thành viên. Dán mã dài 19 chữ số hay mã số ngắn đều được. |
| `reply_quote` | Trả lời kèm trích dẫn tin gốc | không | Câu trả lời của AI trích dẫn đúng tin vừa hỏi (như zalo_bot). Chỉ với tin chữ; không trích được thì gửi tin thường. |
| `reply_prefix` | Tiền tố câu trả lời | không | Chữ thêm vào đầu câu trả lời của AI, ví dụ `Bot-Hass:`. |
| `announce` | Báo ra loa khi có cuộc gọi đến | không | Bật thì khi người này gọi đến, một loa trong nhà đọc «Có cuộc gọi ... từ ...» để người trong nhà biết (kể cả khi không tự nghe máy). Mặc định TẮT. |
| `announce_to` | Loa dùng để báo | không | Loa đọc thông báo cuộc gọi đến (bắt buộc khi bật báo ra loa). Giọng đọc lấy từ Trợ lý giọng nói của quy tắc. |
| `announce_text` | Câu báo ra loa | không | Có thể dùng {ten} (tên người gọi) và {loai} (thoại hoặc video). Bỏ trống = «Có cuộc gọi {loai} từ {ten}.» |
| `announce_volume` | Âm lượng lúc báo (%) | không | Âm lượng của loa khi đọc thông báo có cuộc gọi đến. 0 = giữ nguyên. Không ai nghe máy thì loa trở về mức cũ; có người nghe thì cuộc gọi tự đặt âm lượng của nó. Loa R1 có 15 mức: 6/15 là 40%. |
| `announce_repeat` | Báo lại sau mỗi (giây) | không | Đọc xong thông báo thì chờ chừng này giây rồi đọc lại, cứ thế tới khi có người nghe máy hoặc cuộc gọi kết thúc. 0 = chỉ báo một lần. |
| `connect_now` | Thiết bị nhà dùng NGAY khi người nhận nghe máy | không | Tích ô nào thì thứ đó bật ngay khi người nhận nghe máy, không chờ người nhà nói trực tiếp (ví dụ tích Camera để người nhận thấy hình trong nhà ngay, còn Mic và Loa chỉ bật khi người nhà nói). Tích Camera = cuộc gọi VIDEO. Không tích gì = chưa bật gì (mặc định). Chỉ bật được thiết bị đã chọn ở các ô Loa, Mic, Camera. |
| `video_request` | Khi người gọi xin chuyển sang video | không | Người đang gọi thoại có thể xin chuyển sang video. Mặc định KHÔNG tự đồng ý (riêng tư): chỉ báo cho automation qua sự kiện zalo_call_call_state (trạng thái video_request). Chọn đồng ý nếu muốn tự động, nhưng chỉ có tác dụng khi công tắc «Cho phép đồng ý chuyển sang video» trên thiết bị Zalo Call đang BẬT (mặc định TẮT). |
| `connect` | Thiết bị nhà dùng khi người nhà nói trực tiếp | không | Tích ô nào thì dùng thứ đó: tích 1 = dùng 1, tích 2 = dùng 2, tích 3 = dùng cả 3. Không tích gì = không dùng thiết bị nào (mặc định, người lạ không nghe hay thấy được trong nhà). Tích Camera = cuộc gọi VIDEO. «AI tự chọn» = AI quyết dùng mic và loa hay thêm cả camera, chỉ trong các ô đã tích. Chỉ dùng được thiết bị đã chọn ở các ô Loa, Mic, Camera bên dưới. Thiết bị chỉ bật khi người nhà nói trực tiếp, lúc AI còn đang giữ máy thì chưa bật. |
| `speaker` | Loa trong nhà | không | Loa phát tiếng người gọi khi người nhà nói trực tiếp. |
| `mic` | Mic trong nhà | không | Camera hoặc vệ tinh Assist có mic, gửi tiếng trong nhà cho người gọi khi người nhà nói trực tiếp. |
| `mic_url` | Mic từ địa chỉ mạng (nâng cao) | không | Địa chỉ rtsp/http của luồng tiếng, nếu mic không có trong danh sách. Thắng ô Mic. |
| `camera` | Camera trong nhà | không | Camera gửi hình cho người gọi khi người nhà nói trực tiếp (cuộc gọi video). |
| `volume` | Âm lượng loa (%) | không | Từ 0 đến 100. 0 = giữ nguyên. |
| `echo_guard` | Chống vọng âm | không | Tránh tiếng loa lọt ngược vào mic khi hai thứ cùng một thiết bị. |

**Các lựa chọn:**

- **Áp dụng cho** (`scope`)
  - `thread`: Một người hoặc một nhóm cụ thể
  - `tag`: Mọi người mang một thẻ (điền ô Thẻ)
  - `groups`: Mọi nhóm
  - `contacts`: Mọi người trong danh bạ
  - `strangers`: Mọi người lạ
- **Nghe loại cuộc gọi nào** (`call_types`) - chọn được nhiều ô cùng lúc
  - `voice`: nghe cuộc gọi thoại
  - `video`: nghe cuộc gọi video (chọn cả hai = nghe cả hai loại)
- **Thiết bị nhà dùng NGAY khi người nhận nghe máy** (`connect_now`) - chọn được nhiều ô cùng lúc
  - `mic`: bật mic ngay khi người nhận nghe máy
  - `speaker`: bật loa ngay khi người nhận nghe máy
  - `camera`: bật camera ngay khi người nhận nghe máy (và là cuộc gọi VIDEO)
- **Khi người gọi xin chuyển sang video** (`video_request`)
  - `ask`: không tự đồng ý: chỉ báo cho automation (trạng thái video_request), bạn hoặc blueprint quyết định (mặc định)
  - `accept`: tự đồng ý chuyển sang video nhưng KHÔNG gửi hình trong nhà (người gọi thấy bạn, không thấy nhà)
  - `accept_camera`: tự đồng ý và gửi camera đã chọn trong quy tắc
- **Thiết bị nhà dùng khi người nhà nói trực tiếp** (`connect`) - chọn được nhiều ô cùng lúc
  - `mic`: Mic: gửi tiếng trong nhà cho người gọi
  - `speaker`: Loa: phát tiếng người gọi ra loa trong nhà
  - `camera`: Camera: gửi hình trong nhà (tích ô này là cuộc gọi VIDEO; cuộc thoại được nâng lên video)
  - `ai`: AI tự chọn: AI quyết dùng mic + loa hay thêm camera, chỉ trong các ô đã tích (không ô nào thì trong cả ba; AI không chọn thì chỉ mic + loa)
- **Chống vọng âm** (`echo_guard`)
  - `auto`: chỉ chặn mic khi mic và loa là cùng một thiết bị (ví dụ loa R1)
  - `on`: luôn chặn mic khi loa đang phát tiếng bên kia
  - `duplex`: song công: nói chen được (loa R1 dùng bộ khử vọng riêng)
  - `off`: tắt chống vọng

---

<a id="remove_rule"></a>
#### Xoá quy tắc — `zalo_call.remove_rule`

Xoá quy tắc của một người/nhóm cụ thể hoặc của một nhóm đối tượng. Từ đó hệ thống quay về «không làm gì» với họ.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_rule
data:
  scope: "thread"   # bắt buộc - Áp dụng cho
  thread_id: "..."  # tuỳ chọn - Mã Zalo của người hoặc nhóm
  tag: "..."        # tuỳ chọn - Thẻ
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `scope` | Áp dụng cho | có | Chọn đối tượng của quy tắc. «Một người hoặc một nhóm cụ thể» thì điền thêm Mã Zalo bên dưới. |
| `thread_id` | Mã Zalo của người hoặc nhóm | không | Chỉ cần khi chọn «Một người hoặc một nhóm cụ thể». Xem danh sách bằng dịch vụ «Xem danh bạ Zalo». |
| `tag` | Thẻ | không | Chỉ cần khi chọn «Mọi người mang một thẻ». Gắn thẻ cho người bằng dịch vụ «Gắn thẻ và ghi chú cho người». |

**Các lựa chọn:**

- **Áp dụng cho** (`scope`)
  - `thread`: Một người hoặc một nhóm cụ thể
  - `tag`: Mọi người mang một thẻ (điền ô Thẻ)
  - `groups`: Mọi nhóm
  - `contacts`: Mọi người trong danh bạ
  - `strangers`: Mọi người lạ

---

<a id="list_rules"></a>
#### Xem các quy tắc — `zalo_call.list_rules`

Trả về mọi quy tắc đang đặt.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.list_rules
```

---

<a id="list_contacts"></a>
#### Xem danh bạ Zalo — `zalo_call.list_contacts`

Danh sách bạn bè và nhóm kèm mã Zalo, để điền vào các ô «Mã Zalo».

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.list_contacts
```

---

## Tin nhắn

<a id="send_message"></a>
#### send_message — `zalo_call.send_message`

Gửi tin nhắn Zalo

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_message
data:
  thread_id: "5841349563795164131"    # bắt buộc - Mã hội thoại (threadId)
  type: "user"                        # tuỳ chọn - Loại hội thoại
  message: "Hello từ Home Assistant"  # bắt buộc - Nội dung tin nhắn
  mentions: {}                        # tuỳ chọn - Nhắc người trong NHÓM (chỉ áp dụng khi gửi vào nhóm): danh s
  format: "plain"                     # tuỳ chọn - Định dạng chữ: plain (mặc định) hoặc markdown — **đậm**, *ng
  auto_emphasis: "red"                # tuỳ chọn - Tự nhấn mạnh con số (29°C, 75%, 15:30) và chữ đậm bằng màu: 
  emoji: "ok"                         # tuỳ chọn - Emoji chèn vào đầu tin: chọn trong bảng hoặc gõ emoji bất kỳ
  auto_emoji: false                   # tuỳ chọn - Tự thêm emoji hợp ngữ cảnh vào đầu từng dòng chưa có emoji (
  font_size: "off"                    # tuỳ chọn - Cỡ chữ cho tin này (ghi đè mặc định trên thiết bị): off, sma
  text_color: "off"                   # tuỳ chọn - Màu chữ cho tin này: off, auto (con số), red, orange, yellow
  bold: "off"                         # tuỳ chọn - In đậm: off, on, auto (con số). Bỏ trống = theo mặc định
  italic: "off"                       # tuỳ chọn - In nghiêng: off, on, auto (đoạn trong "…" hoặc (…)). Bỏ trốn
  underline: "off"                    # tuỳ chọn - Gạch chân: off, on, auto (liên kết, email). Bỏ trống = theo 
  heading: "off"                      # tuỳ chọn - Tiêu đề: off, on (dòng đầu), auto (dòng đầu ngắn của tin nhi
  ai_style: false                     # tuỳ chọn - true = nhờ trợ lý AI đánh giá ngữ cảnh cho các mục auto của 
  auto_color: "red"                   # tuỳ chọn - Màu dùng cho chế độ auto của «Màu chữ»: red, orange, yellow,
  zalo_emoji: "afraid"                # tuỳ chọn - Emoji của Zalo (bảng emoji trong ô chat Zalo): chọn tên (hea
  recall_after: 0                     # tuỳ chọn - Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mấ
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `message` | Nội dung tin nhắn | có | Nội dung tin nhắn |
| `mentions` | Nhắc người trong NHÓM (chỉ áp dụng khi gửi vào nhóm): danh sách, mỗi mục {uid, name} (tìm «@name» trong tin) hoặc {uid, pos, len}; uid -1 = @Tất cả. Ví dụ: [{"uid": "123456", "name": "Nam"}] với tin «Chào @Nam» | không | Nhắc người trong NHÓM (chỉ áp dụng khi gửi vào nhóm): danh sách, mỗi mục {uid, name} (tìm «@name» trong tin) hoặc {uid, pos, len}; uid -1 = @Tất cả. Ví dụ: [{"uid": "123456", "name": "Nam"}] với tin «Chào @Nam» |
| `format` | Định dạng chữ: plain (mặc định) hoặc markdown — **đậm**, *nghiêng*, __gạch chân__, ~~gạch ngang~~, # tiêu đề (to + đậm), - mục / 1. mục (danh sách), {red}chữ đỏ{/} {orange} {yellow} {green} (hoặc {đỏ} {cam} {vàng} {xanh}), {big}..{/} {small}..{/} | không | Định dạng chữ: plain (mặc định) hoặc markdown — **đậm**, *nghiêng*, __gạch chân__, ~~gạch ngang~~, # tiêu đề (to + đậm), - mục / 1. mục (danh sách), {red}chữ đỏ{/} {orange} {yellow} {green} (hoặc {đỏ} {cam} {vàng} {xanh}), {big}..{/} {small}..{/} |
| `auto_emphasis` | Tự nhấn mạnh con số (29°C, 75%, 15:30) và chữ đậm bằng màu: red, orange, yellow, green (hoặc đỏ, cam, vàng, xanh) hoặc true = đỏ. Để trống = tắt | không | Tự nhấn mạnh con số (29°C, 75%, 15:30) và chữ đậm bằng màu: red, orange, yellow, green (hoặc đỏ, cam, vàng, xanh) hoặc true = đỏ. Để trống = tắt |
| `emoji` | Emoji chèn vào đầu tin: chọn trong bảng hoặc gõ emoji bất kỳ (🎉). Mã :ten: trong chữ (ví dụ :ok:) cũng được đổi thành emoji | không | Emoji chèn vào đầu tin: chọn trong bảng hoặc gõ emoji bất kỳ (🎉). Mã :ten: trong chữ (ví dụ :ok:) cũng được đổi thành emoji |
| `auto_emoji` | Tự thêm emoji hợp ngữ cảnh vào đầu từng dòng chưa có emoji (cảnh báo, lỗi, xong, nhiệt độ, cửa, đèn…). true = bật, false = tắt cho tin này; bỏ trống = theo công tắc «Chữ: tự thêm emoji» trên thiết bị | không | Tự thêm emoji hợp ngữ cảnh vào đầu từng dòng chưa có emoji (cảnh báo, lỗi, xong, nhiệt độ, cửa, đèn…). true = bật, false = tắt cho tin này; bỏ trống = theo công tắc «Chữ: tự thêm emoji» trên thiết bị |
| `font_size` | Cỡ chữ cho tin này (ghi đè mặc định trên thiết bị): off, small, big hoặc auto (tiêu đề to, dòng trong ngoặc nhỏ). Bỏ trống = theo mặc định | không | Cỡ chữ cho tin này (ghi đè mặc định trên thiết bị): off, small, big hoặc auto (tiêu đề to, dòng trong ngoặc nhỏ). Bỏ trống = theo mặc định |
| `text_color` | Màu chữ cho tin này: off, auto (con số), red, orange, yellow, green. Bỏ trống = theo mặc định | không | Màu chữ cho tin này: off, auto (con số), red, orange, yellow, green. Bỏ trống = theo mặc định |
| `bold` | In đậm: off, on, auto (con số). Bỏ trống = theo mặc định | không | In đậm: off, on, auto (con số). Bỏ trống = theo mặc định |
| `italic` | In nghiêng: off, on, auto (đoạn trong "…" hoặc (…)). Bỏ trống = theo mặc định | không | In nghiêng: off, on, auto (đoạn trong "…" hoặc (…)). Bỏ trống = theo mặc định |
| `underline` | Gạch chân: off, on, auto (liên kết, email). Bỏ trống = theo mặc định | không | Gạch chân: off, on, auto (liên kết, email). Bỏ trống = theo mặc định |
| `heading` | Tiêu đề: off, on (dòng đầu), auto (dòng đầu ngắn của tin nhiều dòng; dòng kết thúc «:» thành đề mục). Bỏ trống = theo mặc định | không | Tiêu đề: off, on (dòng đầu), auto (dòng đầu ngắn của tin nhiều dòng; dòng kết thúc «:» thành đề mục). Bỏ trống = theo mặc định |
| `ai_style` | true = nhờ trợ lý AI đánh giá ngữ cảnh cho các mục auto của tin này (thêm vài giây; quá 8 giây thì dùng quy tắc tức thì); false = quy tắc tức thì; bỏ trống = theo công tắc «Chữ: dùng AI đánh giá…» trên thiết bị | không | true = nhờ trợ lý AI đánh giá ngữ cảnh cho các mục auto của tin này (thêm vài giây; quá 8 giây thì dùng quy tắc tức thì); false = quy tắc tức thì; bỏ trống = theo công tắc «Chữ: dùng AI đánh giá…» trên thiết bị |
| `auto_color` | Màu dùng cho chế độ auto của «Màu chữ»: red, orange, yellow, green. Bỏ trống = theo mặc định | không | Màu dùng cho chế độ auto của «Màu chữ»: red, orange, yellow, green. Bỏ trống = theo mặc định |
| `zalo_emoji` | Emoji của Zalo (bảng emoji trong ô chat Zalo): chọn tên (heart, haha, wow, cry…) để chèn mã tương ứng vào đầu tin; Zalo hiện thành ảnh emoji. Dùng được cùng ô Emoji. | không | Emoji của Zalo (bảng emoji trong ô chat Zalo): chọn tên (heart, haha, wow, cry…) để chèn mã tương ứng vào đầu tin; Zalo hiện thành ảnh emoji. Dùng được cùng ô Emoji. |
| `recall_after` | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) | không | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm
- **Định dạng chữ: plain (mặc định) hoặc markdown — **đậm**, *nghiêng*, __gạch chân__, ~~gạch ngang~~, # tiêu đề (to + đậm), - mục / 1. mục (danh sách), {red}chữ đỏ{/} {orange} {yellow} {green} (hoặc {đỏ} {cam} {vàng} {xanh}), {big}..{/} {small}..{/}** (`format`)
  - `plain`: chữ thường, gửi đúng như đã gõ (mặc định)
  - `markdown`: hiểu dấu đánh dấu: **đậm**, *nghiêng*, __gạch chân__, ~~gạch ngang~~, # tiêu đề, danh sách, {red}màu{/}, {big}to{/}
- **Tự nhấn mạnh con số (29°C, 75%, 15:30) và chữ đậm bằng màu: red, orange, yellow, green (hoặc đỏ, cam, vàng, xanh) hoặc true = đỏ. Để trống = tắt** (`auto_emphasis`)
  - `red`: tự tô đỏ cho con số (29°C, 75%, 15:30) và chữ đậm
  - `orange`: tự tô cam cho con số (29°C, 75%, 15:30) và chữ đậm
  - `yellow`: tự tô vàng cho con số (29°C, 75%, 15:30) và chữ đậm
  - `green`: tự tô xanh lá cho con số (29°C, 75%, 15:30) và chữ đậm
- **Emoji chèn vào đầu tin: chọn trong bảng hoặc gõ emoji bất kỳ (🎉). Mã :ten: trong chữ (ví dụ :ok:) cũng được đổi thành emoji** (`emoji`)
  - `ok`: ✅  ok
  - `x`: ❌  x
  - `warn`: ⚠️  warn
  - `alert`: 🚨  alert
  - `info`: ℹ️  info
  - `hoi`: ❓  hoi
  - `idea`: 💡  idea
  - `fire`: 🔥  fire
  - `water`: 💧  water
  - `temp`: 🌡️  temp
  - `sun`: ☀️  sun
  - `rain`: 🌧️  rain
  - `moon`: 🌙  moon
  - `door`: 🚪  door
  - `lock`: 🔒  lock
  - `unlock`: 🔓  unlock
  - `bell`: 🔔  bell
  - `home`: 🏠  home
  - `car`: 🚗  car
  - `wifi`: 📶  wifi
  - `battery`: 🔋  battery
  - `power`: ⚡  power
  - `tv`: 📺  tv
  - `music`: 🎵  music
  - `camera`: 📷  camera
  - `video`: 🎥  video
  - `phone`: 📞  phone
  - `time`: ⏰  time
  - `calendar`: 📅  calendar
  - `heart`: ❤️  heart
  - `like`: 👍  like
  - `clap`: 👏  clap
  - `party`: 🎉  party
  - `star`: ⭐  star
  - `money`: 💰  money
- **Cỡ chữ cho tin này (ghi đè mặc định trên thiết bị): off, small, big hoặc auto (tiêu đề to, dòng trong ngoặc nhỏ). Bỏ trống = theo mặc định** (`font_size`)
  - `off`: không đổi cỡ chữ
  - `small`: chữ nhỏ
  - `big`: chữ to
  - `auto`: tự động: tiêu đề to, dòng trong ngoặc nhỏ
- **Màu chữ cho tin này: off, auto (con số), red, orange, yellow, green. Bỏ trống = theo mặc định** (`text_color`)
  - `off`: không tô màu
  - `auto`: tự động: tô màu con số (màu lấy ở ô «Màu dùng cho chế độ auto»)
  - `red`: chữ màu đỏ
  - `orange`: chữ màu cam
  - `yellow`: chữ màu vàng
  - `green`: chữ màu xanh lá
- **In đậm: off, on, auto (con số). Bỏ trống = theo mặc định** (`bold`)
  - `off`: không in đậm
  - `on`: in đậm cả tin
  - `auto`: tự động: in đậm con số
- **In nghiêng: off, on, auto (đoạn trong "…" hoặc (…)). Bỏ trống = theo mặc định** (`italic`)
  - `off`: không in nghiêng
  - `on`: in nghiêng cả tin
  - `auto`: tự động: in nghiêng con số
- **Gạch chân: off, on, auto (liên kết, email). Bỏ trống = theo mặc định** (`underline`)
  - `off`: không gạch chân
  - `on`: gạch chân cả tin
  - `auto`: tự động: gạch chân con số
- **Tiêu đề: off, on (dòng đầu), auto (dòng đầu ngắn của tin nhiều dòng; dòng kết thúc «:» thành đề mục). Bỏ trống = theo mặc định** (`heading`)
  - `off`: không làm tiêu đề
  - `on`: dòng đầu thành tiêu đề (to, đậm)
  - `auto`: tự động: dòng đầu ngắn của tin nhiều dòng thành tiêu đề; dòng kết thúc bằng «:» thành đề mục
- **Màu dùng cho chế độ auto của «Màu chữ»: red, orange, yellow, green. Bỏ trống = theo mặc định** (`auto_color`)
  - `red`: màu đỏ dùng cho chế độ auto của «Màu chữ»
  - `orange`: màu cam dùng cho chế độ auto của «Màu chữ»
  - `yellow`: màu vàng dùng cho chế độ auto của «Màu chữ»
  - `green`: màu xanh lá dùng cho chế độ auto của «Màu chữ»
- **Emoji của Zalo (bảng emoji trong ô chat Zalo): chọn tên (heart, haha, wow, cry…) để chèn mã tương ứng vào đầu tin; Zalo hiện thành ảnh emoji. Dùng được cùng ô Emoji.** (`zalo_emoji`)
  - `afraid`: biểu tượng cảm xúc Zalo tên «afraid» (giữ nguyên tên tiếng Anh)
  - `angry`: biểu tượng cảm xúc Zalo tên «angry» (giữ nguyên tên tiếng Anh)
  - `angry_face`: biểu tượng cảm xúc Zalo tên «angry_face» (giữ nguyên tên tiếng Anh)
  - `anguish`: biểu tượng cảm xúc Zalo tên «anguish» (giữ nguyên tên tiếng Anh)
  - `bad`: biểu tượng cảm xúc Zalo tên «bad» (giữ nguyên tên tiếng Anh)
  - `beer`: biểu tượng cảm xúc Zalo tên «beer» (giữ nguyên tên tiếng Anh)
  - `big_laugh`: biểu tượng cảm xúc Zalo tên «big_laugh» (giữ nguyên tên tiếng Anh)
  - `big_smile`: biểu tượng cảm xúc Zalo tên «big_smile» (giữ nguyên tên tiếng Anh)
  - `birthday`: biểu tượng cảm xúc Zalo tên «birthday» (giữ nguyên tên tiếng Anh)
  - `bomb`: biểu tượng cảm xúc Zalo tên «bomb» (giữ nguyên tên tiếng Anh)
  - `broken_heart`: biểu tượng cảm xúc Zalo tên «broken_heart» (giữ nguyên tên tiếng Anh)
  - `bye`: biểu tượng cảm xúc Zalo tên «bye» (giữ nguyên tên tiếng Anh)
  - `confused`: biểu tượng cảm xúc Zalo tên «confused» (giữ nguyên tên tiếng Anh)
  - `cool`: biểu tượng cảm xúc Zalo tên «cool» (giữ nguyên tên tiếng Anh)
  - `cry`: biểu tượng cảm xúc Zalo tên «cry» (giữ nguyên tên tiếng Anh)
  - `dig`: biểu tượng cảm xúc Zalo tên «dig» (giữ nguyên tên tiếng Anh)
  - `dislike`: biểu tượng cảm xúc Zalo tên «dislike» (giữ nguyên tên tiếng Anh)
  - `embarrassed`: biểu tượng cảm xúc Zalo tên «embarrassed» (giữ nguyên tên tiếng Anh)
  - `f_chair`: biểu tượng cảm xúc Zalo tên «f_chair» (giữ nguyên tên tiếng Anh)
  - `fade`: biểu tượng cảm xúc Zalo tên «fade» (giữ nguyên tên tiếng Anh)
  - `haha`: biểu tượng cảm xúc Zalo tên «haha» (giữ nguyên tên tiếng Anh)
  - `handclap`: biểu tượng cảm xúc Zalo tên «handclap» (giữ nguyên tên tiếng Anh)
  - `heart`: biểu tượng cảm xúc Zalo tên «heart» (giữ nguyên tên tiếng Anh)
  - `kiss`: biểu tượng cảm xúc Zalo tên «kiss» (giữ nguyên tên tiếng Anh)
  - `l_chair`: biểu tượng cảm xúc Zalo tên «l_chair» (giữ nguyên tên tiếng Anh)
  - `like`: biểu tượng cảm xúc Zalo tên «like» (giữ nguyên tên tiếng Anh)
  - `love`: biểu tượng cảm xúc Zalo tên «love» (giữ nguyên tên tiếng Anh)
  - `love_you`: biểu tượng cảm xúc Zalo tên «love_you» (giữ nguyên tên tiếng Anh)
  - `nerd`: biểu tượng cảm xúc Zalo tên «nerd» (giữ nguyên tên tiếng Anh)
  - `neutral`: biểu tượng cảm xúc Zalo tên «neutral» (giữ nguyên tên tiếng Anh)
  - `no`: biểu tượng cảm xúc Zalo tên «no» (giữ nguyên tên tiếng Anh)
  - `ok`: biểu tượng cảm xúc Zalo tên «ok» (giữ nguyên tên tiếng Anh)
  - `peace`: biểu tượng cảm xúc Zalo tên «peace» (giữ nguyên tên tiếng Anh)
  - `pray`: biểu tượng cảm xúc Zalo tên «pray» (giữ nguyên tên tiếng Anh)
  - `punch`: biểu tượng cảm xúc Zalo tên «punch» (giữ nguyên tên tiếng Anh)
  - `r_chair`: biểu tượng cảm xúc Zalo tên «r_chair» (giữ nguyên tên tiếng Anh)
  - `rich`: biểu tượng cảm xúc Zalo tên «rich» (giữ nguyên tên tiếng Anh)
  - `rose`: biểu tượng cảm xúc Zalo tên «rose» (giữ nguyên tên tiếng Anh)
  - `sad`: biểu tượng cảm xúc Zalo tên «sad» (giữ nguyên tên tiếng Anh)
  - `sad2`: biểu tượng cảm xúc Zalo tên «sad2» (giữ nguyên tên tiếng Anh)
  - `sad_face`: biểu tượng cảm xúc Zalo tên «sad_face» (giữ nguyên tên tiếng Anh)
  - `share`: biểu tượng cảm xúc Zalo tên «share» (giữ nguyên tên tiếng Anh)
  - `shit`: biểu tượng cảm xúc Zalo tên «shit» (giữ nguyên tên tiếng Anh)
  - `silent`: biểu tượng cảm xúc Zalo tên «silent» (giữ nguyên tên tiếng Anh)
  - `sleepy`: biểu tượng cảm xúc Zalo tên «sleepy» (giữ nguyên tên tiếng Anh)
  - `sun`: biểu tượng cảm xúc Zalo tên «sun» (giữ nguyên tên tiếng Anh)
  - `sunglasses`: biểu tượng cảm xúc Zalo tên «sunglasses» (giữ nguyên tên tiếng Anh)
  - `surprise`: biểu tượng cảm xúc Zalo tên «surprise» (giữ nguyên tên tiếng Anh)
  - `tears_of_joy`: biểu tượng cảm xúc Zalo tên «tears_of_joy» (giữ nguyên tên tiếng Anh)
  - `thanks`: biểu tượng cảm xúc Zalo tên «thanks» (giữ nguyên tên tiếng Anh)
  - `very_sad`: biểu tượng cảm xúc Zalo tên «very_sad» (giữ nguyên tên tiếng Anh)
  - `wink`: biểu tượng cảm xúc Zalo tên «wink» (giữ nguyên tên tiếng Anh)
  - `wipe`: biểu tượng cảm xúc Zalo tên «wipe» (giữ nguyên tên tiếng Anh)
  - `wow`: biểu tượng cảm xúc Zalo tên «wow» (giữ nguyên tên tiếng Anh)

---

<a id="send_file"></a>
#### send_file — `zalo_call.send_file`

Gửi một file bất kỳ qua URL hoặc từ đường dẫn cục bộ.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_file
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  file: "/config/www/document.pdf"  # bắt buộc - Đường dẫn tệp trong HA hoặc URL
  recall_after: 0                   # tuỳ chọn - Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mấ
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `file` | Đường dẫn tệp trong HA hoặc URL | có | Đường dẫn file trên Home Assistant hoặc URL của file cần gửi. |
| `recall_after` | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) | không | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="send_image"></a>
#### send_image — `zalo_call.send_image`

Gửi ảnh Zalo

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_image
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  file: "/config/www/img.png"       # bắt buộc - Ảnh (đường dẫn trong HA hoặc URL)
  recall_after: 0                   # tuỳ chọn - Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mấ
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `file` | Ảnh (đường dẫn trong HA hoặc URL) | có | Đường dẫn file ảnh trên Home Assistant |
| `recall_after` | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) | không | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="send_image_to_user"></a>
#### send_image_to_user — `zalo_call.send_image_to_user`

Gửi 1 ảnh đến user

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_image_to_user
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  file: ""                          # bắt buộc - Ảnh (đường dẫn hoặc URL)
  recall_after: 0                   # tuỳ chọn - Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mấ
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `file` | Ảnh (đường dẫn hoặc URL) | có | Đường dẫn ảnh |
| `recall_after` | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) | không | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="send_images_to_user"></a>
#### send_images_to_user — `zalo_call.send_images_to_user`

Gửi nhiều ảnh đến user

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_images_to_user
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  files: ""                         # bắt buộc - Các ảnh, cách nhau dấu phẩy. Gửi MỘT LÚC thành một album: ản
  recall_after: 0                   # tuỳ chọn - Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mấ
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `files` | Các ảnh, cách nhau dấu phẩy. Gửi MỘT LÚC thành một album: ảnh jpg/png/webp từ 2 tấm trở lên gộp chung, GIF và tệp khác gửi rời | có | Danh sách paths (comma-separated) |
| `recall_after` | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) | không | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="send_image_to_group"></a>
#### send_image_to_group — `zalo_call.send_image_to_group`

Gửi 1 ảnh đến group

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_image_to_group
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  file: ""                          # bắt buộc - Ảnh (đường dẫn hoặc URL)
  recall_after: 0                   # tuỳ chọn - Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mấ
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `file` | Ảnh (đường dẫn hoặc URL) | có | Đường dẫn ảnh |
| `recall_after` | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) | không | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="send_images_to_group"></a>
#### send_images_to_group — `zalo_call.send_images_to_group`

Gửi nhiều ảnh đến group

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_images_to_group
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  files: ""                         # bắt buộc - Các ảnh, cách nhau dấu phẩy. Gửi MỘT LÚC thành một album: ản
  recall_after: 0                   # tuỳ chọn - Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mấ
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `files` | Các ảnh, cách nhau dấu phẩy. Gửi MỘT LÚC thành một album: ảnh jpg/png/webp từ 2 tấm trở lên gộp chung, GIF và tệp khác gửi rời | có | Danh sách paths (comma-separated) |
| `recall_after` | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) | không | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="undo_message"></a>
#### Thu hồi tin nhắn — `zalo_call.undo_message`

Thu hồi tin nhắn đã gửi

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.undo_message
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  msg_id: "msg123456"               # bắt buộc - ID tin nhắn
  cli_msg_id: "1712345678901"       # tuỳ chọn - Client ID tin nhắn
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `msg_id` | ID tin nhắn | có | ID của tin nhắn cần thu hồi |
| `cli_msg_id` | Client ID tin nhắn | không | cliMsgId của chính tin nhắn đó (Zalo cần cả hai mã mới thu hồi được). Sự kiện tin nhắn gửi về automation có sẵn trường này. Bỏ trống thì dùng lại msg_id, có trường hợp Zalo từ chối. |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="send_voice"></a>
#### send_voice — `zalo_call.send_voice`

Gửi tin nhắn thoại: từ tệp âm thanh, hoặc để TTS của Home Assistant đọc chữ

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_voice
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  file: "/config/www/voice.mp3"     # bắt buộc - Tệp âm thanh (đường dẫn hoặc URL)
  recall_after: 0                   # tuỳ chọn - Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mấ
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `file` | Tệp âm thanh (đường dẫn hoặc URL) | có | Tệp âm thanh: đường dẫn trong HA, URL http(s):// hoặc media-source://. Bỏ trống nếu dùng message |
| `recall_after` | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) | không | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="get_group_chat_history"></a>
#### Xem lịch sử nhóm — `zalo_call.get_group_chat_history`

Lấy lịch sử tin nhắn của một nhóm

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_group_chat_history
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  count: 50                         # tuỳ chọn - Số tin (tối đa 1000)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `count` | Số tin (tối đa 1000) | không | Số lượng tin nhắn muốn lấy (mặc định 50, tối đa 1000) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="add_reaction"></a>
#### Thả reaction — `zalo_call.add_reaction`

Thả cảm xúc vào một tin nhắn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.add_reaction
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  icon: "afraid"                    # bắt buộc - Icon (like/heart/haha/...)
  msg_id: "msg123456"               # bắt buộc - ID tin nhắn
  cli_msg_id: "cli123456"           # bắt buộc - Client ID tin nhắn
  r_icon: "..."                     # tuỳ chọn - rIcon (khi icon chưa map)
  r_type: "..."                     # tuỳ chọn - rType (khi icon chưa map)
  msg_type: "..."                   # tuỳ chọn - Loại tin (mặc định 1=text)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `icon` | Icon (like/heart/haha/...) | có | Tên cảm xúc |
| `msg_id` | ID tin nhắn | có | ID tin nhắn cần thả cảm xúc |
| `cli_msg_id` | Client ID tin nhắn | có | ID client của tin nhắn |
| `r_icon` | rIcon (khi icon chưa map) | không | rIcon (khi icon chưa map) |
| `r_type` | rType (khi icon chưa map) | không | rType (khi icon chưa map) |
| `msg_type` | Loại tin (mặc định 1=text) | không | Loại tin (mặc định 1=text) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm
- **Icon (like/heart/haha/...)** (`icon`)
  - `afraid`: biểu tượng cảm xúc Zalo tên «afraid» (giữ nguyên tên tiếng Anh)
  - `angry`: biểu tượng cảm xúc Zalo tên «angry» (giữ nguyên tên tiếng Anh)
  - `angry_face`: biểu tượng cảm xúc Zalo tên «angry_face» (giữ nguyên tên tiếng Anh)
  - `anguish`: biểu tượng cảm xúc Zalo tên «anguish» (giữ nguyên tên tiếng Anh)
  - `bad`: biểu tượng cảm xúc Zalo tên «bad» (giữ nguyên tên tiếng Anh)
  - `beer`: biểu tượng cảm xúc Zalo tên «beer» (giữ nguyên tên tiếng Anh)
  - `big_laugh`: biểu tượng cảm xúc Zalo tên «big_laugh» (giữ nguyên tên tiếng Anh)
  - `big_smile`: biểu tượng cảm xúc Zalo tên «big_smile» (giữ nguyên tên tiếng Anh)
  - `birthday`: biểu tượng cảm xúc Zalo tên «birthday» (giữ nguyên tên tiếng Anh)
  - `bomb`: biểu tượng cảm xúc Zalo tên «bomb» (giữ nguyên tên tiếng Anh)
  - `broken_heart`: biểu tượng cảm xúc Zalo tên «broken_heart» (giữ nguyên tên tiếng Anh)
  - `bye`: biểu tượng cảm xúc Zalo tên «bye» (giữ nguyên tên tiếng Anh)
  - `confused`: biểu tượng cảm xúc Zalo tên «confused» (giữ nguyên tên tiếng Anh)
  - `cool`: biểu tượng cảm xúc Zalo tên «cool» (giữ nguyên tên tiếng Anh)
  - `cry`: biểu tượng cảm xúc Zalo tên «cry» (giữ nguyên tên tiếng Anh)
  - `dig`: biểu tượng cảm xúc Zalo tên «dig» (giữ nguyên tên tiếng Anh)
  - `dislike`: biểu tượng cảm xúc Zalo tên «dislike» (giữ nguyên tên tiếng Anh)
  - `embarrassed`: biểu tượng cảm xúc Zalo tên «embarrassed» (giữ nguyên tên tiếng Anh)
  - `f_chair`: biểu tượng cảm xúc Zalo tên «f_chair» (giữ nguyên tên tiếng Anh)
  - `fade`: biểu tượng cảm xúc Zalo tên «fade» (giữ nguyên tên tiếng Anh)
  - `haha`: biểu tượng cảm xúc Zalo tên «haha» (giữ nguyên tên tiếng Anh)
  - `handclap`: biểu tượng cảm xúc Zalo tên «handclap» (giữ nguyên tên tiếng Anh)
  - `heart`: biểu tượng cảm xúc Zalo tên «heart» (giữ nguyên tên tiếng Anh)
  - `kiss`: biểu tượng cảm xúc Zalo tên «kiss» (giữ nguyên tên tiếng Anh)
  - `l_chair`: biểu tượng cảm xúc Zalo tên «l_chair» (giữ nguyên tên tiếng Anh)
  - `like`: biểu tượng cảm xúc Zalo tên «like» (giữ nguyên tên tiếng Anh)
  - `love`: biểu tượng cảm xúc Zalo tên «love» (giữ nguyên tên tiếng Anh)
  - `love_you`: biểu tượng cảm xúc Zalo tên «love_you» (giữ nguyên tên tiếng Anh)
  - `nerd`: biểu tượng cảm xúc Zalo tên «nerd» (giữ nguyên tên tiếng Anh)
  - `neutral`: biểu tượng cảm xúc Zalo tên «neutral» (giữ nguyên tên tiếng Anh)
  - `no`: biểu tượng cảm xúc Zalo tên «no» (giữ nguyên tên tiếng Anh)
  - `ok`: biểu tượng cảm xúc Zalo tên «ok» (giữ nguyên tên tiếng Anh)
  - `peace`: biểu tượng cảm xúc Zalo tên «peace» (giữ nguyên tên tiếng Anh)
  - `pray`: biểu tượng cảm xúc Zalo tên «pray» (giữ nguyên tên tiếng Anh)
  - `punch`: biểu tượng cảm xúc Zalo tên «punch» (giữ nguyên tên tiếng Anh)
  - `r_chair`: biểu tượng cảm xúc Zalo tên «r_chair» (giữ nguyên tên tiếng Anh)
  - `rich`: biểu tượng cảm xúc Zalo tên «rich» (giữ nguyên tên tiếng Anh)
  - `rose`: biểu tượng cảm xúc Zalo tên «rose» (giữ nguyên tên tiếng Anh)
  - `sad`: biểu tượng cảm xúc Zalo tên «sad» (giữ nguyên tên tiếng Anh)
  - `sad2`: biểu tượng cảm xúc Zalo tên «sad2» (giữ nguyên tên tiếng Anh)
  - `sad_face`: biểu tượng cảm xúc Zalo tên «sad_face» (giữ nguyên tên tiếng Anh)
  - `share`: biểu tượng cảm xúc Zalo tên «share» (giữ nguyên tên tiếng Anh)
  - `shit`: biểu tượng cảm xúc Zalo tên «shit» (giữ nguyên tên tiếng Anh)
  - `silent`: biểu tượng cảm xúc Zalo tên «silent» (giữ nguyên tên tiếng Anh)
  - `sleepy`: biểu tượng cảm xúc Zalo tên «sleepy» (giữ nguyên tên tiếng Anh)
  - `sun`: biểu tượng cảm xúc Zalo tên «sun» (giữ nguyên tên tiếng Anh)
  - `sunglasses`: biểu tượng cảm xúc Zalo tên «sunglasses» (giữ nguyên tên tiếng Anh)
  - `surprise`: biểu tượng cảm xúc Zalo tên «surprise» (giữ nguyên tên tiếng Anh)
  - `tears_of_joy`: biểu tượng cảm xúc Zalo tên «tears_of_joy» (giữ nguyên tên tiếng Anh)
  - `thanks`: biểu tượng cảm xúc Zalo tên «thanks» (giữ nguyên tên tiếng Anh)
  - `very_sad`: biểu tượng cảm xúc Zalo tên «very_sad» (giữ nguyên tên tiếng Anh)
  - `wink`: biểu tượng cảm xúc Zalo tên «wink» (giữ nguyên tên tiếng Anh)
  - `wipe`: biểu tượng cảm xúc Zalo tên «wipe» (giữ nguyên tên tiếng Anh)
  - `wow`: biểu tượng cảm xúc Zalo tên «wow» (giữ nguyên tên tiếng Anh)

---

<a id="delete_message"></a>
#### Xóa tin nhắn — `zalo_call.delete_message`

Xóa một tin nhắn (chỉ ở phía mình)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.delete_message
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  msg_id: "msg123456"               # bắt buộc - ID tin nhắn
  cli_msg_id: "cli123456"           # tuỳ chọn - Client ID tin nhắn
  only_me: true                     # tuỳ chọn - Chỉ xóa phía mình (true/false)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `msg_id` | ID tin nhắn | có | ID tin nhắn cần xóa |
| `cli_msg_id` | Client ID tin nhắn | không | ID client của tin nhắn |
| `only_me` | Chỉ xóa phía mình (true/false) | không | Chỉ xóa ở phía mình |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="forward_message"></a>
#### Chuyển tiếp tin nhắn — `zalo_call.forward_message`

Chuyển tiếp một tin nhắn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.forward_message
data:
  message: "..."          # bắt buộc - Nội dung chữ cần chuyển tiếp
  ttl: 0                  # tuỳ chọn - TTL (ms, 0 = không tự xóa)
  dest_thread_ids: "..."  # bắt buộc - Thread đích (cách nhau bằng dấu phẩy)
  type: "user"            # tuỳ chọn - Loại thread đích (user/group)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `message` | Nội dung chữ cần chuyển tiếp | có | Nội dung tin nhắn gốc (mã hóa) |
| `ttl` | TTL (ms, 0 = không tự xóa) | không | Thời gian tự hủy (milliseconds) |
| `dest_thread_ids` | Thread đích (cách nhau bằng dấu phẩy) | có | Thread đích (cách nhau bằng dấu phẩy) |
| `type` | Loại thread đích (user/group) | không | Loại cuộc trò chuyện nhận tin nhắn |

**Các lựa chọn:**

- **Loại thread đích (user/group)** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="parse_link"></a>
#### Phân tích link lấy preview — `zalo_call.parse_link`

Phân tích link để lấy thông tin preview

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.parse_link
data:
  link: "https://example.com"  # bắt buộc - Link
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `link` | Link | có | URL cần phân tích |

---

<a id="send_card"></a>
#### send_card — `zalo_call.send_card`

Gửi danh thiếp của một người dùng

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_card
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  user_id: "5841349563795164131"    # bắt buộc - UserId của danh thiếp
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `user_id` | UserId của danh thiếp | có | ID người dùng của danh thiếp |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="send_link"></a>
#### send_link — `zalo_call.send_link`

Gửi một tin nhắn chứa liên kết có preview

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_link
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  link: "https://example.com"       # bắt buộc - Đường link
  message: ""                       # tuỳ chọn - Lời nhắn kèm theo
  recall_after: 0                   # tuỳ chọn - Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mấ
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `link` | Đường link | có | URL cần gửi |
| `message` | Lời nhắn kèm theo | không | Nội dung tin nhắn đi kèm |
| `recall_after` | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) | không | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="send_video"></a>
#### send_video — `zalo_call.send_video`

Gửi video qua URL hoặc từ đường dẫn cục bộ

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_video
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  file: "/config/www/video.mp4"     # bắt buộc - Video: đường dẫn trong HA (thư mục www hoặc media) hoặc URL 
  thumbnail: ""                     # tuỳ chọn - Ảnh bìa: đường dẫn hoặc URL. Bỏ trống = tự tìm «…_thumb.jpg»
  message: ""                       # tuỳ chọn - Chú thích kèm video (bỏ trống = không)
  width: 1280                       # tuỳ chọn - Độ rộng (px). Bỏ trống = tự đo bằng ffprobe
  height: 720                       # tuỳ chọn - Độ cao (px). Bỏ trống = tự đo bằng ffprobe
  duration: 0                       # tuỳ chọn - Thời lượng (giây). Bỏ trống = tự đo bằng ffprobe
  recall_after: 0                   # tuỳ chọn - Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mấ
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `file` | Video: đường dẫn trong HA (thư mục www hoặc media) hoặc URL công khai. Gửi dạng video phát được trong chat; tệp trong HA được cấp địa chỉ công khai từ địa chỉ ngoài của HA (media có chữ ký hạn 1 giờ). Không có địa chỉ công khai thì gửi dạng tệp đính kèm | có | Đường dẫn file video trên Home Assistant hoặc URL của video cần gửi |
| `thumbnail` | Ảnh bìa: đường dẫn hoặc URL. Bỏ trống = tự tìm «…_thumb.jpg» cạnh video, không có thì dùng chính video | không | URL thumbnail tùy chỉnh |
| `message` | Chú thích kèm video (bỏ trống = không) | không | Tin nhắn kèm theo |
| `width` | Độ rộng (px). Bỏ trống = tự đo bằng ffprobe | không | Chiều rộng video (pixels) |
| `height` | Độ cao (px). Bỏ trống = tự đo bằng ffprobe | không | Chiều cao video (pixels) |
| `duration` | Thời lượng (giây). Bỏ trống = tự đo bằng ffprobe | không | Thời gian tắt thông báo |
| `recall_after` | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) | không | Tự thu hồi sau N giây (0 hoặc bỏ trống = không). Tin biến mất ở cả hai bên đúng giờ, nhưng Zalo để lại dòng «tin nhắn đã được thu hồi». Hẹn giờ nằm trong app nên vẫn chạy khi HA khởi động lại; tối đa 86400 giây (1 ngày) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="quote_message"></a>
#### Trích dẫn tin nhắn — `zalo_call.quote_message`

Trích dẫn tin nhắn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.quote_message
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  msg_id: "msg123456"               # bắt buộc - ID tin nhắn
  text: "..."                       # bắt buộc - Nội dung trích dẫn
  qmsg_owner: "..."                 # bắt buộc - UID người gửi tin gốc
  qmsg_cli_id: "..."                # tuỳ chọn - Client ID tin gốc
  qmsg_type: "..."                  # tuỳ chọn - Loại tin gốc
  qmsg_ts: "..."                    # tuỳ chọn - Timestamp tin gốc
  qmsg: "..."                       # tuỳ chọn - Nội dung tin gốc
  ttl: 0                            # tuỳ chọn - TTL (1-1)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `msg_id` | ID tin nhắn | có | ID của tin nhắn cần thu hồi |
| `text` | Nội dung trích dẫn | có | Nội dung trích dẫn |
| `qmsg_owner` | UID người gửi tin gốc | có | UID người gửi tin gốc |
| `qmsg_cli_id` | Client ID tin gốc | không | Client ID tin gốc |
| `qmsg_type` | Loại tin gốc | không | Loại tin gốc |
| `qmsg_ts` | Timestamp tin gốc | không | Timestamp tin gốc |
| `qmsg` | Nội dung tin gốc | không | Nội dung tin gốc |
| `ttl` | TTL (1-1) | không | Thời gian tự hủy (milliseconds) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="mark_seen"></a>
#### Đánh dấu đã xem / đã nhận — `zalo_call.mark_seen`

Đánh dấu đã xem / đã nhận

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.mark_seen
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  msg_ids: "..."                    # bắt buộc - ID tin nhắn (cách nhau bằng dấu phẩy)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `msg_ids` | ID tin nhắn (cách nhau bằng dấu phẩy) | có | ID tin nhắn (cách nhau bằng dấu phẩy) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="fetch_important"></a>
#### Xem tin nhắn quan trọng — `zalo_call.fetch_important`

Xem tin nhắn quan trọng

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.fetch_important
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

## Tài khoản và webhook

<a id="get_logged_accounts"></a>
#### get_logged_accounts — `zalo_call.get_logged_accounts`

Lấy danh sách tài khoản Zalo đã login

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_logged_accounts
```

---

<a id="get_account_details"></a>
#### get_account_details — `zalo_call.get_account_details`

Lấy chi tiết một tài khoản Zalo

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_account_details
```

---

<a id="get_account_webhooks"></a>
#### get_account_webhooks — `zalo_call.get_account_webhooks`

Lấy tất cả config webhook

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_account_webhooks
```

---

<a id="get_account_webhook"></a>
#### get_account_webhook — `zalo_call.get_account_webhook`

Lấy config webhook cho account

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_account_webhook
```

---

<a id="set_account_webhook"></a>
#### set_account_webhook — `zalo_call.set_account_webhook`

Cập nhật config webhook

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.set_account_webhook
data:
  message_webhook_url: ""      # tuỳ chọn - URL webhook tin nhắn
  group_event_webhook_url: ""  # tuỳ chọn - URL webhook sự kiện nhóm
  reaction_webhook_url: ""     # tuỳ chọn - URL webhook cảm xúc
  call_webhook_url: "..."      # tuỳ chọn - URL webhook cuộc gọi
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `message_webhook_url` | URL webhook tin nhắn | không | URL cho message |
| `group_event_webhook_url` | URL webhook sự kiện nhóm | không | URL cho group event |
| `reaction_webhook_url` | URL webhook cảm xúc | không | URL cho reaction |
| `call_webhook_url` | URL webhook cuộc gọi | không | URL webhook cuộc gọi |

---

<a id="delete_account_webhook"></a>
#### delete_account_webhook — `zalo_call.delete_account_webhook`

Xóa config webhook

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.delete_account_webhook
```

---

<a id="get_proxies"></a>
#### get_proxies — `zalo_call.get_proxies`

Lấy danh sách proxy

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_proxies
```

---

<a id="add_proxy"></a>
#### add_proxy — `zalo_call.add_proxy`

Thêm proxy mới

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.add_proxy
```

---

<a id="remove_proxy"></a>
#### remove_proxy — `zalo_call.remove_proxy`

Xóa proxy

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_proxy
```

---

<a id="get_login_qr"></a>
#### get_login_qr — `zalo_call.get_login_qr`

Lấy mã QR đăng nhập Zalo từ server và hiển thị lên thông báo.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_login_qr
```

---

## Hồ sơ và bạn bè

<a id="find_user"></a>
#### Tìm người dùng theo SĐT — `zalo_call.find_user`

Tìm user bằng số điện thoại

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.find_user
data:
  phone: ""  # bắt buộc - Số điện thoại
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `phone` | Số điện thoại | có | Số điện thoại |

---

<a id="get_user_info"></a>
#### Xem thông tin người dùng — `zalo_call.get_user_info`

Lấy thông tin user

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_user_info
data:
  user_id: ""  # bắt buộc - UserId (nhiều id cách nhau bằng dấu phẩy)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `user_id` | UserId (nhiều id cách nhau bằng dấu phẩy) | có | User ID |

---

<a id="send_friend_request"></a>
#### Gửi lời mời kết bạn — `zalo_call.send_friend_request`

Gửi lời mời kết bạn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_friend_request
data:
  user_id: ""                                # bắt buộc - UserId
  message: "Xin chào, hãy kết bạn với tôi!"  # tuỳ chọn - Lời nhắn
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `user_id` | UserId | có | User ID |
| `message` | Lời nhắn | không | Tin nhắn mời |

---

<a id="accept_friend_request"></a>
#### Chấp nhận kết bạn — `zalo_call.accept_friend_request`

Chấp nhận lời mời kết bạn từ một người dùng

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.accept_friend_request
data:
  user_id: "5841349563795164131"  # bắt buộc - UserId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `user_id` | UserId | có | ID người dùng đã gửi lời mời kết bạn |

---

<a id="block_user"></a>
#### Chặn người dùng — `zalo_call.block_user`

Chặn một người dùng

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.block_user
data:
  user_id: "5841349563795164131"  # bắt buộc - UserId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `user_id` | UserId | có | ID người dùng cần chặn |

---

<a id="unblock_user"></a>
#### Bỏ chặn người dùng — `zalo_call.unblock_user`

Bỏ chặn một người dùng

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.unblock_user
data:
  user_id: "5841349563795164131"  # bắt buộc - UserId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `user_id` | UserId | có | ID người dùng cần bỏ chặn |

---

<a id="get_all_friends"></a>
#### get_all_friends — `zalo_call.get_all_friends`

Lấy danh sách tất cả bạn bè

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_all_friends
```

---

<a id="get_sent_friend_requests"></a>
#### Xem lời mời kết bạn đã gửi — `zalo_call.get_sent_friend_requests`

Lấy danh sách lời mời kết bạn đã gửi

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_sent_friend_requests
```

---

<a id="undo_friend_request"></a>
#### Thu hồi lời mời kết bạn — `zalo_call.undo_friend_request`

Thu hồi lời mời kết bạn đã gửi

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.undo_friend_request
data:
  friend_id: "5841349563795164131"  # bắt buộc - UserId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `friend_id` | UserId | có | ID người dùng đã gửi lời mời |

---

<a id="remove_friend"></a>
#### Hủy kết bạn — `zalo_call.remove_friend`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

Hủy kết bạn với một người dùng (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_friend
data:
  friend_id: "5841349563795164131"  # bắt buộc - UserId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `friend_id` | UserId | có | ID người bạn cần hủy kết bạn |

---

<a id="change_friend_alias"></a>
#### Đổi biệt danh — `zalo_call.change_friend_alias`

Thay đổi biệt danh của một người bạn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.change_friend_alias
data:
  friend_id: "5841349563795164131"  # bắt buộc - UserId
  alias: "Bạn thân"                 # bắt buộc - Biệt danh mới
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `friend_id` | UserId | có | ID người bạn cần đổi biệt danh |
| `alias` | Biệt danh mới | có | Biệt danh mới |

---

<a id="remove_friend_alias"></a>
#### Xóa biệt danh — `zalo_call.remove_friend_alias`

Xóa biệt danh của một người bạn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_friend_alias
data:
  friend_id: "5841349563795164131"  # bắt buộc - UserId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `friend_id` | UserId | có | ID người bạn cần xóa biệt danh |

---

<a id="get_all_groups"></a>
#### get_all_groups — `zalo_call.get_all_groups`

Lấy danh sách tất cả nhóm đã tham gia

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_all_groups
```

---

<a id="update_profile"></a>
#### Cập nhật thông tin cá nhân — `zalo_call.update_profile`

Cập nhật thông tin cá nhân

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_profile
data:
  name: "Nguyễn Văn A"  # tuỳ chọn - Tên hiển thị
  dob: "1990-01-01"     # tuỳ chọn - Ngày sinh (yyyy-mm-dd)
  gender: 0             # tuỳ chọn - Giới tính (0=Nam, 1=Nữ)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `name` | Tên hiển thị | không | Tên mới |
| `dob` | Ngày sinh (yyyy-mm-dd) | không | Ngày sinh (yyyy-mm-dd) |
| `gender` | Giới tính (0=Nam, 1=Nữ) | không | Giới tính |

**Các lựa chọn:**

- **Giới tính (0=Nam, 1=Nữ)** (`gender`)
  - `0`: nam
  - `1`: nữ

---

<a id="update_settings"></a>
#### Cập nhật cài đặt riêng tư — `zalo_call.update_settings`

Cập nhật cài đặt riêng tư

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_settings
data:
  setting_type: "online_status"  # bắt buộc - Tên cài đặt (vd show_online_status, display_seen_status, rec
  status: 1                      # bắt buộc - Giá trị (1=bật, 0=tắt)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `setting_type` | Tên cài đặt (vd show_online_status, display_seen_status, receive_message...) | có | Loại cài đặt |
| `status` | Giá trị (1=bật, 0=tắt) | có | Trạng thái |

**Các lựa chọn:**

- **Tên cài đặt (vd show_online_status, display_seen_status, receive_message...)** (`setting_type`)
  - `online_status`: cài đặt hiện trạng thái đang hoạt động
  - `seen_status`: cài đặt hiện «đã xem» tin nhắn
  - `receive_message`: cài đặt ai được nhắn tin cho mình
  - `phone_search`: cài đặt cho người khác tìm mình bằng số điện thoại
- **Giá trị (1=bật, 0=tắt)** (`status`)
  - `1`: bật
  - `0`: tắt

---

<a id="block_view_feed"></a>
#### Chặn xem nhật ký — `zalo_call.block_view_feed`

Chặn/bỏ chặn một người bạn xem nhật ký

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.block_view_feed
data:
  user_id: "5841349563795164131"  # bắt buộc - UserId
  is_block_feed: false            # bắt buộc - Chặn (true/false)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `user_id` | UserId | có | ID người bạn |
| `is_block_feed` | Chặn (true/false) | có | Chặn hoặc bỏ chặn |

---

<a id="change_account_avatar"></a>
#### Đổi ảnh đại diện — `zalo_call.change_account_avatar`

Thay đổi ảnh đại diện

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.change_account_avatar
data:
  file: "..."  # bắt buộc - Ảnh đại diện (upload file)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `file` | Ảnh đại diện (upload file) | có | Ảnh đại diện (upload file) |

---

<a id="get_avatar_list"></a>
#### Xem ảnh đại diện đã dùng — `zalo_call.get_avatar_list`

Lấy danh sách các ảnh đại diện đã sử dụng

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_avatar_list
data:
  count: "10"  # tuỳ chọn - Số lượng
  page: "1"    # tuỳ chọn - Trang
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `count` | Số lượng | không | Số lượng ảnh tối đa cần lấy |
| `page` | Trang | không | Trang dữ liệu cần lấy |

---

<a id="last_online"></a>
#### Xem hoạt động cuối — `zalo_call.last_online`

Xem thời gian hoạt động cuối cùng của một người dùng

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.last_online
data:
  user_id: "5841349563795164131"  # bắt buộc - UserId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `user_id` | UserId | có | ID người dùng cần xem |

---

<a id="reject_friend_request"></a>
#### Từ chối lời mời kết bạn — `zalo_call.reject_friend_request`

Từ chối lời mời kết bạn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.reject_friend_request
data:
  user_id: ""  # bắt buộc - UserId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `user_id` | UserId | có | User ID |

---

<a id="get_settings"></a>
#### Xem cài đặt riêng tư — `zalo_call.get_settings`

Xem cài đặt riêng tư

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_settings
```

---

## Nhóm

<a id="create_group"></a>
#### Tạo nhóm mới — `zalo_call.create_group`

Tạo group mới

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.create_group
data:
  name: ""           # bắt buộc - Tên nhóm
  member_ids: "..."  # tuỳ chọn - Thành viên (userId, cách nhau bằng dấu phẩy)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `name` | Tên nhóm | có | Tên group |
| `member_ids` | Thành viên (userId, cách nhau bằng dấu phẩy) | không | Thành viên (userId, cách nhau bằng dấu phẩy) |

---

<a id="get_group_info"></a>
#### Xem thông tin nhóm — `zalo_call.get_group_info`

Lấy info group

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_group_info
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="add_user_to_group"></a>
#### Mời thành viên vào nhóm — `zalo_call.add_user_to_group`

Thêm thành viên vào group

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.add_user_to_group
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  member_id: ""                     # bắt buộc - UserId (cách nhau bằng dấu phẩy)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `member_id` | UserId (cách nhau bằng dấu phẩy) | có | Member ID (comma-separated for multiple) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="remove_user_from_group"></a>
#### Đuổi thành viên — `zalo_call.remove_user_from_group`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

Xóa thành viên khỏi group (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_user_from_group
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  member_id: ""                     # bắt buộc - UserId (cách nhau bằng dấu phẩy)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `member_id` | UserId (cách nhau bằng dấu phẩy) | có | Member ID (comma-separated for multiple) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="change_group_name"></a>
#### Đổi tên nhóm — `zalo_call.change_group_name`

Đổi tên nhóm

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.change_group_name
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  name: "Nhóm mới"                  # bắt buộc - Tên mới
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `name` | Tên mới | có | Tên mới của nhóm |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="change_group_avatar"></a>
#### Đổi ảnh đại diện nhóm — `zalo_call.change_group_avatar`

Đổi ảnh đại diện nhóm

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.change_group_avatar
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  file: "/config/www/avatar.png"    # bắt buộc - Ảnh đại diện (upload file)
  width: 1280                       # tuỳ chọn - Chiều rộng ảnh
  height: 720                       # tuỳ chọn - Chiều cao ảnh
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `file` | Ảnh đại diện (upload file) | có | Đường dẫn đến ảnh mới |
| `width` | Chiều rộng ảnh | không | Chiều rộng video (pixels) |
| `height` | Chiều cao ảnh | không | Chiều cao video (pixels) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="add_group_deputy"></a>
#### Thêm phó nhóm — `zalo_call.add_group_deputy`

Thêm phó nhóm

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.add_group_deputy
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  member_id: "5841349563795164131"  # bắt buộc - UserId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `member_id` | UserId | có | ID thành viên cần thêm làm phó nhóm |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="remove_group_deputy"></a>
#### Xóa phó nhóm — `zalo_call.remove_group_deputy`

Xóa phó nhóm

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_group_deputy
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  member_id: "5841349563795164131"  # bắt buộc - UserId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `member_id` | UserId | có | ID thành viên cần xóa quyền phó nhóm |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="change_group_owner"></a>
#### Chuyển quyền sở hữu nhóm — `zalo_call.change_group_owner`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

Chuyển quyền sở hữu nhóm (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.change_group_owner
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  member_id: "5841349563795164131"  # bắt buộc - UserId chủ mới
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `member_id` | UserId chủ mới | có | ID thành viên được chuyển quyền sở hữu |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="disperse_group"></a>
#### Giải tán nhóm — `zalo_call.disperse_group`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

Giải tán nhóm (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.disperse_group
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="enable_group_link"></a>
#### Bật link tham gia nhóm — `zalo_call.enable_group_link`

Kích hoạt và lấy link tham gia nhóm

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.enable_group_link
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="disable_group_link"></a>
#### Tắt link tham gia nhóm — `zalo_call.disable_group_link`

Vô hiệu hóa link tham gia nhóm

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.disable_group_link
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="join_group"></a>
#### Tham gia nhóm bằng link — `zalo_call.join_group`

Tham gia nhóm bằng link mời

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.join_group
data:
  link: "https://zalo.me/g/abcxyz"  # bắt buộc - Link mời
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `link` | Link mời | có | Link mời tham gia nhóm |

---

<a id="leave_group"></a>
#### Rời nhóm — `zalo_call.leave_group`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

Rời khỏi nhóm (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.leave_group
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  silent: false                     # tuỳ chọn - Rời lặng lẽ (true/false)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `silent` | Rời lặng lẽ (true/false) | không | Rời nhóm trong im lặng |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="create_note_group"></a>
#### Tạo ghi chú trong nhóm — `zalo_call.create_note_group`

Tạo ghi chú mới trong nhóm

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.create_note_group
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  title: "..."                      # bắt buộc - Tiêu đề ghi chú
  pin_act: true                     # tuỳ chọn - Ghim (true/false)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `title` | Tiêu đề ghi chú | có | Tiêu đề ghi chú |
| `pin_act` | Ghim (true/false) | không | Ghim ghi chú |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="edit_note_group"></a>
#### Sửa ghi chú trong nhóm — `zalo_call.edit_note_group`

Chỉnh sửa ghi chú trong nhóm

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.edit_note_group
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  topic_id: "topic123456"           # bắt buộc - ID ghi chú
  title: "..."                      # bắt buộc - Tiêu đề mới
  pin_act: true                     # tuỳ chọn - Ghim (true/false)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `topic_id` | ID ghi chú | có | ID của ghi chú |
| `title` | Tiêu đề mới | có | Nội dung ghi chú mới |
| `pin_act` | Ghim (true/false) | không | Ghim ghi chú |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="get_list_board"></a>
#### Xem bảng tin của nhóm — `zalo_call.get_list_board`

Lấy danh sách các mục trên bảng tin của nhóm

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_list_board
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="create_poll"></a>
#### Tạo bình chọn — `zalo_call.create_poll`

Tạo một cuộc bình chọn trong nhóm

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.create_poll
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  question: "Chọn thời gian họp?"   # bắt buộc - Câu hỏi
  options: "Thứ 2,Thứ 3,Thứ 4"      # bắt buộc - Lựa chọn (cách nhau bằng dấu phẩy)
  allow_multi_choices: false        # tuỳ chọn - Cho chọn nhiều (true/false)
  allow_add_new_option: "..."       # tuỳ chọn - Cho thêm lựa chọn mới (mặc định true)
  is_anonymous: "..."               # tuỳ chọn - Bình chọn ẩn danh (true/false)
  hide_vote_preview: "..."          # tuỳ chọn - Ẩn kết quả khi chưa bình chọn (true/false)
  expired_time: "..."               # tuỳ chọn - Hạn chót (ms epoch, 0 = không hết hạn)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `question` | Câu hỏi | có | Câu hỏi bình chọn |
| `options` | Lựa chọn (cách nhau bằng dấu phẩy) | có | Các lựa chọn (phân cách bởi dấu phẩy) |
| `allow_multi_choices` | Cho chọn nhiều (true/false) | không | Cho phép chọn nhiều lựa chọn |
| `allow_add_new_option` | Cho thêm lựa chọn mới (mặc định true) | không | Cho thêm lựa chọn mới (mặc định true) |
| `is_anonymous` | Bình chọn ẩn danh (true/false) | không | Bình chọn ẩn danh (true/false) |
| `hide_vote_preview` | Ẩn kết quả khi chưa bình chọn (true/false) | không | Ẩn kết quả khi chưa bình chọn (true/false) |
| `expired_time` | Hạn chót (ms epoch, 0 = không hết hạn) | không | Hạn chót (ms epoch, 0 = không hết hạn) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="get_poll_detail"></a>
#### Xem chi tiết bình chọn — `zalo_call.get_poll_detail`

Lấy thông tin chi tiết của một cuộc bình chọn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_poll_detail
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  poll_id: 123456789                # bắt buộc - ID bình chọn
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `poll_id` | ID bình chọn | có | ID số của cuộc bình chọn (zca-js) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="lock_poll"></a>
#### Khóa bình chọn — `zalo_call.lock_poll`

Khóa một cuộc bình chọn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.lock_poll
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  poll_id: "123456789"              # bắt buộc - ID bình chọn
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `poll_id` | ID bình chọn | có | ID của cuộc bình chọn |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="get_group_link"></a>
#### Xem link nhóm — `zalo_call.get_group_link`

Xem link nhóm

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_group_link
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="vote_poll"></a>
#### Bỏ phiếu bình chọn — `zalo_call.vote_poll`

Bỏ phiếu bình chọn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.vote_poll
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  poll_id: 123456789                # bắt buộc - ID bình chọn
  option_ids: "..."                 # bắt buộc - ID lựa chọn (cách nhau bằng dấu phẩy)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `poll_id` | ID bình chọn | có | ID số của cuộc bình chọn (zca-js) |
| `option_ids` | ID lựa chọn (cách nhau bằng dấu phẩy) | có | ID lựa chọn (cách nhau bằng dấu phẩy) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

## Sticker

<a id="send_sticker"></a>
#### Gửi sticker — `zalo_call.send_sticker`

Gửi sticker

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_sticker
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  sticker_id: 1234                  # tuỳ chọn - Sticker ID
  cate_id: "..."                    # tuỳ chọn - Cate ID
  sticker_type: "..."               # tuỳ chọn - Type
  keyword: "/qm1"                   # tuỳ chọn - Từ khoá sticker
  pick: "first"                     # tuỳ chọn - Chọn kết quả
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `sticker_id` | Sticker ID | không | ID số của sticker (zca-js) |
| `cate_id` | Cate ID | không | Cate ID |
| `sticker_type` | Type | không | Type |
| `keyword` | Từ khoá sticker | không | Gõ từ khoá (ví dụ: cảm ơn, haha, yêu) — tự tìm sticker rồi gửi; dùng thay cho Sticker ID / Cate ID. |
| `pick` | Chọn kết quả | không | first = kết quả đầu (mặc định), random = chọn ngẫu nhiên trong các kết quả. |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm
- **Chọn kết quả** (`pick`)
  - `first`: lấy kết quả đầu tiên (mặc định)
  - `random`: chọn ngẫu nhiên trong các kết quả

---

<a id="get_stickers"></a>
#### Xem danh mục sticker — `zalo_call.get_stickers`

Tìm kiếm sticker theo từ khóa

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_stickers
```

---

<a id="get_stickers_detail"></a>
#### Xem chi tiết bộ sticker — `zalo_call.get_stickers_detail`

Lấy thông tin chi tiết của một bộ sticker

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_stickers_detail
data:
  sticker_album: "22148"  # bắt buộc - Album/Cate ID
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `sticker_album` | Album/Cate ID | có | ID album sticker |

---

## Nhắc hẹn

<a id="create_reminder"></a>
#### Tạo nhắc hẹn — `zalo_call.create_reminder`

Tạo nhắc nhở mới

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.create_reminder
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  title: "Họp nhóm"                 # bắt buộc - Tiêu đề
  content: "Họp nhóm lúc 10h sáng"  # tuỳ chọn - Nội dung
  remind_time: "1632739200000"      # bắt buộc - Thời gian nhắc (ISO-8601 hoặc epoch)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `title` | Tiêu đề | có | Tiêu đề nhắc nhở |
| `content` | Nội dung | không | Nội dung nhắc nhở |
| `remind_time` | Thời gian nhắc (ISO-8601 hoặc epoch) | có | Thời gian nhắc nhở (timestamp) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="remove_reminder"></a>
#### Xóa nhắc hẹn — `zalo_call.remove_reminder`

Xóa nhắc nhở

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_reminder
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  reminder_id: "reminder123"        # bắt buộc - ID nhắc hẹn
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `reminder_id` | ID nhắc hẹn | có | ID của nhắc nhở cần xóa |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="edit_reminder"></a>
#### Sửa nhắc hẹn — `zalo_call.edit_reminder`

Chỉnh sửa một nhắc hẹn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.edit_reminder
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  topic_id: "reminder123456"        # bắt buộc - ID nhắc hẹn
  title: "Họp online"               # bắt buộc - Tiêu đề mới
  remind_time: "1632739200000"      # tuỳ chọn - Thời gian nhắc mới
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `topic_id` | ID nhắc hẹn | có | ID của nhắc hẹn |
| `title` | Tiêu đề mới | có | Tiêu đề mới |
| `remind_time` | Thời gian nhắc mới | không | Thời gian nhắc nhở (timestamp) |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="get_reminder"></a>
#### Xem chi tiết nhắc hẹn — `zalo_call.get_reminder`

Lấy thông tin chi tiết của một nhắc hẹn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_reminder
data:
  reminder_id: "reminder123456"  # bắt buộc - ID nhắc hẹn
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `reminder_id` | ID nhắc hẹn | có | ID của nhắc hẹn |

---

<a id="get_list_reminder"></a>
#### Xem danh sách nhắc hẹn — `zalo_call.get_list_reminder`

Lấy danh sách các nhắc hẹn trong một cuộc trò chuyện

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_list_reminder
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="get_reminder_responses"></a>
#### Xem phản hồi nhắc hẹn — `zalo_call.get_reminder_responses`

Lấy danh sách phản hồi cho một nhắc hẹn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_reminder_responses
data:
  reminder_id: "reminder123456"  # bắt buộc - ID nhắc hẹn
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `reminder_id` | ID nhắc hẹn | có | ID của nhắc hẹn |

---

<a id="add_quick_message"></a>
#### Thêm tin nhắn nhanh — `zalo_call.add_quick_message`

Thêm một tin nhắn nhanh mới

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.add_quick_message
data:
  keyword: "/qm1"              # bắt buộc - Từ khóa
  title: "Xin chào mọi người"  # bắt buộc - Nội dung
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `keyword` | Từ khóa | có | Từ khóa để gọi tin nhắn nhanh |
| `title` | Nội dung | có | Nội dung tin nhắn nhanh |

---

<a id="get_quick_message"></a>
#### Xem tin nhắn nhanh — `zalo_call.get_quick_message`

Lấy danh sách tin nhắn nhanh

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_quick_message
```

---

<a id="remove_quick_message"></a>
#### Xóa tin nhắn nhanh — `zalo_call.remove_quick_message`

Xóa tin nhắn nhanh

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_quick_message
data:
  item_ids: "12345678"  # bắt buộc - ID (cách nhau bằng dấu phẩy)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `item_ids` | ID (cách nhau bằng dấu phẩy) | có | ID hoặc danh sách ID tin nhắn nhanh cần xóa |

---

<a id="update_quick_message"></a>
#### Sửa tin nhắn nhanh — `zalo_call.update_quick_message`

Cập nhật tin nhắn nhanh

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_quick_message
data:
  item_id: "12345678"                        # bắt buộc - ID
  keyword: "/qm1_updated"                    # tuỳ chọn - Từ khóa
  title: "Xin chào mọi người (đã cập nhật)"  # tuỳ chọn - Nội dung
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `item_id` | ID | có | ID tin nhắn nhanh |
| `keyword` | Từ khóa | không | Từ khóa mới |
| `title` | Nội dung | không | Nội dung mới |

---

## Hội thoại

<a id="set_mute"></a>
#### Tắt thông báo — `zalo_call.set_mute`

Tắt thông báo cho cuộc trò chuyện

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.set_mute
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  duration: 3600                    # bắt buộc - Thời lượng giây (3600/14400/-1=vĩnh viễn/0=bật lại)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `duration` | Thời lượng giây (3600/14400/-1=vĩnh viễn/0=bật lại) | có | Thời gian tắt thông báo |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm
- **Thời lượng giây (3600/14400/-1=vĩnh viễn/0=bật lại)** (`duration`)
  - `3600`: tắt thông báo 1 giờ
  - `14400`: tắt thông báo 4 giờ
  - `-1`: tắt thông báo vĩnh viễn
  - `0`: bật lại thông báo

---

<a id="set_pinned_conversation"></a>
#### Ghim/bỏ ghim hội thoại — `zalo_call.set_pinned_conversation`

Ghim hoặc bỏ ghim cuộc trò chuyện

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.set_pinned_conversation
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  pinned: false                     # bắt buộc - Ghim (true/false)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `pinned` | Ghim (true/false) | có | Ghim hay bỏ ghim |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="get_unread_mark"></a>
#### Xem hội thoại chưa đọc — `zalo_call.get_unread_mark`

Lấy danh sách các cuộc trò chuyện được đánh dấu là chưa đọc

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_unread_mark
```

---

<a id="add_unread_mark"></a>
#### Đánh dấu hội thoại chưa đọc — `zalo_call.add_unread_mark`

Đánh dấu một cuộc trò chuyện là chưa đọc

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.add_unread_mark
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="remove_unread_mark"></a>
#### Bỏ đánh dấu chưa đọc — `zalo_call.remove_unread_mark`

Bỏ đánh dấu chưa đọc cho một cuộc trò chuyện

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_unread_mark
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="delete_chat"></a>
#### Xóa hội thoại — `zalo_call.delete_chat`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

Xóa một cuộc trò chuyện khỏi danh sách (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.delete_chat
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  cli_msg_id: "1712345678901"       # tuỳ chọn - Client ID tin cuối
  conver: "..."                     # tuỳ chọn - Conver của tin cuối
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `cli_msg_id` | Client ID tin cuối | không | cliMsgId của chính tin nhắn đó (Zalo cần cả hai mã mới thu hồi được). Sự kiện tin nhắn gửi về automation có sẵn trường này. Bỏ trống thì dùng lại msg_id, có trường hợp Zalo từ chối. |
| `conver` | Conver của tin cuối | không | Conver của tin cuối |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="get_archived_chat_list"></a>
#### Xem hội thoại đã lưu trữ — `zalo_call.get_archived_chat_list`

Lấy danh sách các cuộc trò chuyện đã được lưu trữ

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_archived_chat_list
```

---

<a id="get_auto_delete_chat"></a>
#### Xem hội thoại đang tự xóa — `zalo_call.get_auto_delete_chat`

Lấy danh sách các cuộc trò chuyện đang bật tự động xóa tin nhắn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_auto_delete_chat
```

---

<a id="update_auto_delete_chat"></a>
#### Bật/tắt tự xóa tin nhắn — `zalo_call.update_auto_delete_chat`

Bật/tắt chế độ tự động xóa tin nhắn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_auto_delete_chat
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  ttl: 0                            # bắt buộc - TTL (0=tắt, 86400000=1 ngày, 604800000=7 ngày)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `ttl` | TTL (0=tắt, 86400000=1 ngày, 604800000=7 ngày) | có | Thời gian tự xóa |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm
- **TTL (0=tắt, 86400000=1 ngày, 604800000=7 ngày)** (`ttl`)
  - `0`: tắt tự xoá tin
  - `86400000`: tự xoá sau 1 ngày (tính bằng mili giây)
  - `604800000`: tự xoá sau 7 ngày (tính bằng mili giây)

---

<a id="get_hidden_conversations"></a>
#### Xem hội thoại ẩn — `zalo_call.get_hidden_conversations`

Lấy danh sách các cuộc trò chuyện đang bị ẩn bằng mã PIN

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_hidden_conversations
```

---

<a id="set_hidden_conversations"></a>
#### Ẩn/bỏ ẩn hội thoại — `zalo_call.set_hidden_conversations`

Ẩn hoặc bỏ ẩn một cuộc trò chuyện

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.set_hidden_conversations
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
  hidden: false                     # bắt buộc - Ẩn (true/false)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |
| `hidden` | Ẩn (true/false) | có | Ẩn hoặc hiện cuộc trò chuyện |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="update_hidden_convers_pin"></a>
#### Đặt PIN hội thoại ẩn — `zalo_call.update_hidden_convers_pin`

Đặt hoặc thay đổi mã PIN cho các cuộc trò chuyện ẩn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_hidden_convers_pin
data:
  pin: "1234"  # bắt buộc - PIN mới
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `pin` | PIN mới | có | Mã PIN mới |

---

<a id="reset_hidden_convers_pin"></a>
#### Gỡ PIN hội thoại ẩn — `zalo_call.reset_hidden_convers_pin`

Gỡ bỏ mã PIN cho các cuộc trò chuyện ẩn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.reset_hidden_convers_pin
```

---

<a id="get_mute"></a>
#### Xem danh sách tắt thông báo — `zalo_call.get_mute`

Lấy danh sách các cuộc trò chuyện đang bị tắt thông báo

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_mute
```

---

<a id="get_pin_conversations"></a>
#### Xem hội thoại đã ghim — `zalo_call.get_pin_conversations`

Lấy danh sách các cuộc trò chuyện đã được ghim

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_pin_conversations
```

---

## Nhãn và «đang nhập»

<a id="get_labels"></a>
#### Xem danh sách nhãn — `zalo_call.get_labels`

Lấy danh sách các nhãn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_labels
```

---

<a id="send_typing_event"></a>
#### Gửi trạng thái đang gõ — `zalo_call.send_typing_event`

Gửi thông báo đang soạn tin nhắn

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_typing_event
data:
  thread_id: "5841349563795164131"  # bắt buộc - Mã hội thoại (threadId)
  type: "user"                      # tuỳ chọn - Loại hội thoại
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Mã hội thoại (threadId) | có | UserId (1-1) hoặc GroupId (nhóm). |
| `type` | Loại hội thoại | không | user = 1-1, group = nhóm. |

**Các lựa chọn:**

- **Loại hội thoại** (`type`)
  - `user`: trò chuyện 1-1 với một người
  - `group`: nhóm

---

<a id="update_label"></a>
#### Gắn nhãn cho hội thoại — `zalo_call.update_label`

Gắn nhãn cho hội thoại

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_label
data:
  label_data: "..."  # bắt buộc - Danh sách nhãn (JSON) đã sửa, lấy từ get_labels
  version: "..."     # bắt buộc - Version của danh sách nhãn
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `label_data` | Danh sách nhãn (JSON) đã sửa, lấy từ get_labels | có | Danh sách nhãn (JSON) đã sửa, lấy từ get_labels |
| `version` | Version của danh sách nhãn | có | Version của danh sách nhãn |

---

## Phiên và xác thực (nâng cao)

<a id="decrypt_gids"></a>
#### decryptGids — `zalo_call.decrypt_gids`

decryptGids — Giải mã danh sách Global ID (g_...) ẩn danh thành User ID thật (tương ứng hàm getUidFromGlobalNoiseId / command 12054 trên Zalo PC)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.decrypt_gids
data:
  gids: "..."  # bắt buộc - gids
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `gids` | gids | có | Danh sách Global ID (hoặc 1 GID đơn lẻ) (string \| string[]) |

---

<a id="encrypt_gids"></a>
#### encryptGids — `zalo_call.encrypt_gids`

encryptGids — Mã hóa danh sách UID thật sang định danh ẩn danh Global Noise ID (OTDAKO...) (command 12053)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.encrypt_gids
data:
  uids: "..."  # bắt buộc - uids
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `uids` | uids | có | Mảng chuỗi các UID cần mã hóa (string[]) |

---

<a id="export_session"></a>
#### exportSession — `zalo_call.export_session`

exportSession — Xuất toàn bộ thông tin phiên đăng nhập hiện tại (uid, imei, userAgent, language, cookie) dưới định dạng chuẩn Credentials để lưu trữ (JSON/Database) và truyền trực tiếp vào zalo.login(session). (chưa tự động: khong dung dich

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.export_session
```

---

<a id="get_context"></a>
#### getContext — `zalo_call.get_context`

getContext — API getContext thuộc phân hệ auth. (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_context
```

---

<a id="get_cookie"></a>
#### getCookie — `zalo_call.get_cookie`

getCookie — Get the current cookie string (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_cookie
```

---

<a id="get_list_device"></a>
#### getListDevice — `zalo_call.get_list_device`

getListDevice — Lấy danh sách các thiết bị đang đăng nhập tài khoản Zalo hiện tại.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_list_device
```

---

<a id="get_noised_ids"></a>
#### getNoisedIds — `zalo_call.get_noised_ids`

getNoisedIds — Chuyển đổi danh sách UID cá nhân (fids) và GID nhóm (gids) dạng số thuần (từ SQLite ZDB4.0 mobile) sang định dạng Noised ID 19 chữ số dùng trên Zalo Web/PC (getNoisedUids, command 12390). Tự động fallback sang https://zwid.ap

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_noised_ids
```

---

<a id="get_own_id"></a>
#### getOwnId — `zalo_call.get_own_id`

getOwnId — API getOwnId thuộc phân hệ auth. (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_own_id
```

---

<a id="get_q_r"></a>
#### getQR — `zalo_call.get_q_r`

getQR — Lấy mã QR của danh sách người dùng theo UID.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_q_r
data:
  userId: "..."  # bắt buộc - userId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `userId` | userId | có | User ID or list of user IDs (string \| string[]) |

---

<a id="lost_focus"></a>
#### lostFocus — `zalo_call.lost_focus`

lostFocus — Gửi tín hiệu thông báo ứng dụng chuyển sang chế độ chạy nền (Background).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.lost_focus
```

---

<a id="scan_u_r_l"></a>
#### scanURL — `zalo_call.scan_u_r_l`

scanURL — Quét và kiểm tra độ an toàn của đường dẫn URL thông qua bộ lọc bảo mật Zalo.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.scan_u_r_l
data:
  url: "..."  # bắt buộc - url
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `url` | url | có | URL to scan (string) |

---

<a id="update_active_status"></a>
#### updateActiveStatus — `zalo_call.update_active_status`

updateActiveStatus — Cập nhật trạng thái hoạt động (Online / Offline / Ping) của tài khoản. (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_active_status
```

---

<a id="update_lang"></a>
#### updateLang — `zalo_call.update_lang`

updateLang — Cập nhật ngôn ngữ hiển thị của phiên tài khoản Zalo.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_lang
data:
  language: "vi"  # tuỳ chọn - language
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `language` | language | không | language to update (VI, EN) (UpdateLangAvailableLanguages) |

---

## Chat (nâng cao)

<a id="get_block_sharing_conversations"></a>
#### getBlockSharingConversations — `zalo_call.get_block_sharing_conversations`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

getBlockSharingConversations — Lấy danh sách hội thoại đang bật chế độ chặn chia sẻ / chuyển tiếp tin nhắn (command 12178) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_block_sharing_conversations
data:
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="get_conv_offline_messages"></a>
#### getConvOfflineMessages — `zalo_call.get_conv_offline_messages`

getConvOfflineMessages — Lấy danh sách hội thoại nhóm có tin nhắn ngoại tuyến mới (command 12300)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_conv_offline_messages
data:
  queueInfo: "..."  # bắt buộc - queueInfo
  lastMsgId: "..."  # tuỳ chọn - lastMsgId
  lastActId: "..."  # tuỳ chọn - lastActId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `queueInfo` | queueInfo | có | queueInfo (unknown) |
| `lastMsgId` | lastMsgId | không | lastMsgId (string \| number) |
| `lastActId` | lastActId | không | lastActId (string \| number) |

---

<a id="get_direct_message_status"></a>
#### getDirectMessageStatus — `zalo_call.get_direct_message_status`

getDirectMessageStatus — Truy vấn trạng thái Đã nhận (deliver) và Đã xem (seen) tin nhắn trong các hội thoại cá nhân 1-1 (command 12016)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_direct_message_status
data:
  data: "..."  # bắt buộc - data
  params: {}   # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `data` | data | có | Danh sách UID hoặc đối tượng truy vấn `{ tId }` (Array<string \| { tId: string; [key: string]: unknown }>) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_last_seen"></a>
#### getLastSeen — `zalo_call.get_last_seen`

getLastSeen — Lấy thông tin trạng thái đã xem cuối cùng của danh sách nhóm và cá nhân (command 12009)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_last_seen
data:
  groupIds: "..."  # tuỳ chọn - groupIds
  userIds: "..."   # tuỳ chọn - userIds
  params: {}       # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupIds` | groupIds | không | groupIds (string[]) |
| `userIds` | userIds | không | userIds (string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_last_seen_reaction"></a>
#### getLastSeenReaction — `zalo_call.get_last_seen_reaction`

getLastSeenReaction — Lấy trạng thái đã xem cảm xúc (Reaction) cuối cùng của danh sách nhóm và cá nhân (command 12450)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_last_seen_reaction
data:
  groupIds: "..."  # tuỳ chọn - groupIds
  userIds: "..."   # tuỳ chọn - userIds
  params: {}       # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupIds` | groupIds | không | groupIds (string[]) |
| `userIds` | userIds | không | userIds (string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_recent_search_list"></a>
#### getRecentSearchList — `zalo_call.get_recent_search_list`

getRecentSearchList — Lấy danh sách lịch sử tìm kiếm gần đây trên Zalo (command 12125)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_recent_search_list
data:
  version: "..."  # tuỳ chọn - version
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `version` | version | không | Phiên bản lịch sử tìm kiếm (mặc định: 0) (number) |

---

<a id="get_suggested_conversations"></a>
#### getSuggestedConversations — `zalo_call.get_suggested_conversations`

getSuggestedConversations — Lấy danh sách các cuộc hội thoại được gợi ý (command 11233)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_suggested_conversations
data:
  language: "vi"  # tuỳ chọn - language
  params: {}      # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `language` | language | không | Ngôn ngữ hiển thị (mặc định theo `ctx.language` hoặc `"vi"`) (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_translate_setting"></a>
#### getTranslateSetting — `zalo_call.get_translate_setting`

getTranslateSetting — Lấy cấu hình tính năng dịch tin nhắn tự động bằng Zalo AI (command 13395)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_translate_setting
```

---

<a id="mark_sub_tab_seen"></a>
#### markSubTabSeen — `zalo_call.mark_sub_tab_seen`

markSubTabSeen — Đánh dấu đã xem các tab phụ của danh sách hội thoại (command 16214)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.mark_sub_tab_seen
data:
  seens: "..."  # bắt buộc - seens
  params: {}    # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `seens` | seens | có | Danh sách thông tin tab phụ đã xem (unknown[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="preload_conversations"></a>
#### preloadConversations — `zalo_call.preload_conversations`

preloadConversations — Tải trước tin nhắn cuối cùng và trạng thái đã đọc của các hội thoại đang hoạt động (command 10053).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.preload_conversations
data:
  threadIdLocalMsgId: "..."  # tuỳ chọn - threadIdLocalMsgId
  params: {}                 # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `threadIdLocalMsgId` | threadIdLocalMsgId | không | Optional map of `{ [threadId]: lastLocalMsgId }` (defaults to `{}`) (Record<string, string \| number>) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="renew_message_link"></a>
#### renewMessageLink — `zalo_call.renew_message_link`

renewMessageLink — Gia hạn đường dẫn tải tệp đính kèm / đa phương tiện đã hết hạn trong tin nhắn (command 12094)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.renew_message_link
data:
  toId: "..."      # bắt buộc - toId
  msgType: "..."   # bắt buộc - msgType
  msgInfo: "..."   # bắt buộc - msgInfo
  clientId: "..."  # tuỳ chọn - clientId
  isGroup: "..."   # tuỳ chọn - isGroup
  params: {}       # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `toId` | toId | có | toId (string) |
| `msgType` | msgType | có | msgType (number) |
| `msgInfo` | msgInfo | có | msgInfo (Record<string, unknown>) |
| `clientId` | clientId | không | clientId (string \| number) |
| `isGroup` | isGroup | không | isGroup (boolean) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="send_bank_card"></a>
#### sendBankCard — `zalo_call.send_bank_card`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

sendBankCard — Gửi danh thiếp thông tin tài khoản ngân hàng (Bank Card) vào cuộc trò chuyện. (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_bank_card
data:
  payload: "..."   # bắt buộc - payload
  threadId: "..."  # bắt buộc - threadId
  type: 0          # tuỳ chọn - type
  params: {}       # bắt buộc - params
  confirm: false   # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `payload` | payload | có | The payload containing the bank card information (SendBankCardPayload) |
| `threadId` | threadId | có | The ID of the thread to send the bank card to (string) |
| `type` | type | không | The type of thread to send the bank card to (ThreadType) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

**Các lựa chọn:**

- **type** (`type`)
  - `0`: người dùng (trò chuyện 1-1)
  - `1`: nhóm

---

<a id="send_delivered_event"></a>
#### sendDeliveredEvent — `zalo_call.send_delivered_event`

sendDeliveredEvent — Gửi tín hiệu xác nhận Đã nhận (Delivered) cho một hoặc nhiều tin nhắn. (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_delivered_event
```

---

<a id="send_report"></a>
#### sendReport — `zalo_call.send_report`

sendReport — Gửi báo cáo vi phạm (Report Abuse) đối với người dùng hoặc cuộc trò chuyện. (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_report
```

---

<a id="send_seen_event"></a>
#### sendSeenEvent — `zalo_call.send_seen_event`

sendSeenEvent — Gửi tín hiệu xác nhận Đã xem (Seen) cho các tin nhắn trong hội thoại. (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_seen_event
```

---

<a id="set_pinned_conversations"></a>
#### setPinnedConversations — `zalo_call.set_pinned_conversations`

setPinnedConversations — Ghim hoặc bỏ ghim cuộc trò chuyện lên đầu danh sách.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.set_pinned_conversations
data:
  pinned: false    # bắt buộc - pinned
  threadId: "..."  # bắt buộc - threadId
  type: 0          # tuỳ chọn - type
  params: {}       # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `pinned` | pinned | có | Should pin conversations (boolean) |
| `threadId` | threadId | có | The ID(s) of the thread (string \| string[]) |
| `type` | type | không | Type of thread, default User (ThreadType) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

**Các lựa chọn:**

- **type** (`type`)
  - `0`: người dùng (trò chuyện 1-1)
  - `1`: nhóm

---

<a id="translate_message"></a>
#### translateMessage — `zalo_call.translate_message`

translateMessage — Dịch thủ công một tin nhắn văn bản bằng Zalo AI (command 13397)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.translate_message
data:
  reqId: "..."           # tuỳ chọn - reqId
  msgId: "..."           # bắt buộc - msgId
  threadId: "..."        # bắt buộc - threadId
  type: 0                # tuỳ chọn - type
  srcLang: "..."         # bắt buộc - srcLang
  desLang: "..."         # bắt buộc - desLang
  text: "..."            # bắt buộc - text
  immutableItems: "..."  # tuỳ chọn - immutableItems
  params: {}             # tuỳ chọn - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `reqId` | reqId | không | reqId (string) |
| `msgId` | msgId | có | msgId (string) |
| `threadId` | threadId | có | threadId (string) |
| `type` | type | không | type (number) |
| `srcLang` | srcLang | có | srcLang (string) |
| `desLang` | desLang | có | desLang (string) |
| `text` | text | có | text (string) |
| `immutableItems` | immutableItems | không | immutableItems (unknown[]) |
| `params` | params | không | Tuỳ chọn: JSON nguyên khối nếu muốn tự dựng; bỏ trống thì app dựng từ các trường ở trên. |

**Các lựa chọn:**

- **type** (`type`)
  - `0`: mã 0 của Zalo (app chưa chú giải nghĩa; giữ mặc định nếu không chắc)
  - `1`: mã 1 của Zalo (app chưa chú giải nghĩa; giữ mặc định nếu không chắc)

---

<a id="translate_message_auto"></a>
#### translateMessageAuto — `zalo_call.translate_message_auto`

translateMessageAuto — Gửi yêu cầu dịch tự động hàng loạt tin nhắn đến bằng Zalo AI (command 13398). Kết quả dịch bất đồng bộ có thể được đẩy về qua sự kiện api.listener.on("translate_event", ...).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.translate_message_auto
data:
  reqId: "..."     # tuỳ chọn - reqId
  threadId: "..."  # bắt buộc - threadId
  type: 0          # tuỳ chọn - type
  srcLang: "..."   # bắt buộc - srcLang
  desLang: "..."   # bắt buộc - desLang
  msgs: "..."      # bắt buộc - msgs
  params: {}       # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `reqId` | reqId | không | reqId (string) |
| `threadId` | threadId | có | threadId (string) |
| `type` | type | không | type (number) |
| `srcLang` | srcLang | có | srcLang (string) |
| `desLang` | desLang | có | desLang (string) |
| `msgs` | msgs | có | msgs (TranslateMessageAutoItem[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

**Các lựa chọn:**

- **type** (`type`)
  - `0`: mã 0 của Zalo (app chưa chú giải nghĩa; giữ mặc định nếu không chắc)
  - `1`: mã 1 của Zalo (app chưa chú giải nghĩa; giữ mặc định nếu không chắc)

---

<a id="translate_message_suggest"></a>
#### translateMessageSuggest — `zalo_call.translate_message_suggest`

translateMessageSuggest — Gửi yêu cầu dịch gợi ý tin nhắn đang soạn thảo bằng Zalo AI (command 13399). Kết quả dịch bất đồng bộ có thể được đẩy về qua sự kiện api.listener.on("translate_event", ...).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.translate_message_suggest
data:
  reqId: "..."           # tuỳ chọn - reqId
  threadId: "..."        # bắt buộc - threadId
  type: 0                # tuỳ chọn - type
  srcLang: "..."         # bắt buộc - srcLang
  desLang: "..."         # bắt buộc - desLang
  text: "..."            # bắt buộc - text
  immutableItems: "..."  # tuỳ chọn - immutableItems
  params: {}             # tuỳ chọn - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `reqId` | reqId | không | reqId (string) |
| `threadId` | threadId | có | threadId (string) |
| `type` | type | không | type (number) |
| `srcLang` | srcLang | có | srcLang (string) |
| `desLang` | desLang | có | desLang (string) |
| `text` | text | có | text (string) |
| `immutableItems` | immutableItems | không | immutableItems (unknown[]) |
| `params` | params | không | Tuỳ chọn: JSON nguyên khối nếu muốn tự dựng; bỏ trống thì app dựng từ các trường ở trên. |

**Các lựa chọn:**

- **type** (`type`)
  - `0`: mã 0 của Zalo (app chưa chú giải nghĩa; giữ mặc định nếu không chắc)
  - `1`: mã 1 của Zalo (app chưa chú giải nghĩa; giữ mặc định nếu không chắc)

---

<a id="undo"></a>
#### undo — `zalo_call.undo`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

undo — Thu hồi (Undo) một tin nhắn đã gửi với tất cả mọi người trong cuộc trò chuyện. (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet)) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.undo
data:
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="undo_multi_message"></a>
#### undoMultiMessage — `zalo_call.undo_multi_message`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

undoMultiMessage — Thu hồi hàng loạt nhiều tin nhắn cùng lúc trong hội thoại cá nhân hoặc nhóm (command 12115 / 12116) (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet)) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.undo_multi_message
data:
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="update_archived_chat_list"></a>
#### updateArchivedChatList — `zalo_call.update_archived_chat_list`

updateArchivedChatList — Đưa cuộc trò chuyện vào mục Lưu trữ (Archive) hoặc khôi phục ra ngoài.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_archived_chat_list
data:
  isArchived: "..."     # bắt buộc - isArchived
  conversations: "..."  # bắt buộc - conversations
  params: {}            # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `isArchived` | isArchived | có | - true to archive, false to unarchive (boolean) |
| `conversations` | conversations | có | - List of conversations to archive/unarchive (UpdateArchivedChatListTarget \| UpdateArchivedChatListTarget[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="update_block_sharing_conversation"></a>
#### updateBlockSharingConversation — `zalo_call.update_block_sharing_conversation`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

updateBlockSharingConversation — Bật hoặc tắt chế độ chặn chia sẻ / chuyển tiếp tin nhắn trong một hội thoại (command 12179) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_block_sharing_conversation
data:
  threadId: "..."    # bắt buộc - threadId
  isGroup: "..."     # tuỳ chọn - isGroup
  isEnabled: "..."   # bắt buộc - isEnabled
  clientLang: "..."  # tuỳ chọn - clientLang
  params: {}         # bắt buộc - params
  confirm: false     # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `threadId` | threadId | có | threadId (string) |
| `isGroup` | isGroup | không | isGroup (boolean) |
| `isEnabled` | isEnabled | có | isEnabled (boolean \| number) |
| `clientLang` | clientLang | không | clientLang (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="update_pin_conversations"></a>
#### updatePinConversations — `zalo_call.update_pin_conversations`

updatePinConversations — Cập nhật danh sách hội thoại ghim qua /api/pinconvers/update (command 12121) hoặc /api/pinconvers/updatev2 (command 12122) (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_pin_conversations
```

---

<a id="update_recent_search"></a>
#### updateRecentSearch — `zalo_call.update_recent_search`

updateRecentSearch — Cập nhật danh sách lịch sử tìm kiếm gần đây trên Zalo (command 12126)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_recent_search
data:
  listRecent: "..."   # tuỳ chọn - listRecent
  listKeyword: "..."  # tuỳ chọn - listKeyword
  version: "..."      # tuỳ chọn - version
  params: {}          # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `listRecent` | listRecent | không | listRecent (Record<string, unknown>[]) |
| `listKeyword` | listKeyword | không | listKeyword (string[]) |
| `version` | version | không | version (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="update_translate_setting"></a>
#### updateTranslateSetting — `zalo_call.update_translate_setting`

updateTranslateSetting — Cập nhật cấu hình dịch tin nhắn Zalo AI cho một hội thoại (command 13396) (chưa tự động: khong doc duoc doi tuong params)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_translate_setting
data:
  threadId: "..."  # bắt buộc - threadId
  type: 0          # bắt buộc - type
  settings: "..."  # bắt buộc - settings
  auto: "..."      # bắt buộc - auto
  suggest: "..."   # bắt buộc - suggest
  srcLang: "..."   # bắt buộc - srcLang
  desLang: "..."   # bắt buộc - desLang
  key: "..."       # bắt buộc - key
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `threadId` | threadId | có | threadId (string) |
| `type` | type | có | type (number) |
| `settings` | settings | có | settings ({) |
| `auto` | auto | có | auto (boolean \| number) |
| `suggest` | suggest | có | suggest (boolean \| number) |
| `srcLang` | srcLang | có | srcLang (string) |
| `desLang` | desLang | có | desLang (string) |
| `key` | key | có | key (string]: unknown) |

**Các lựa chọn:**

- **type** (`type`)
  - `0`: mã 0 của Zalo (app chưa chú giải nghĩa; giữ mặc định nếu không chắc)
  - `1`: mã 1 của Zalo (app chưa chú giải nghĩa; giữ mặc định nếu không chắc)

---

## Nhóm (nâng cao)

<a id="add_group_blocked_member"></a>
#### addGroupBlockedMember — `zalo_call.add_group_blocked_member`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

addGroupBlockedMember — Chặn một hoặc nhiều thành viên khỏi nhóm (không cho tham gia lại). (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.add_group_blocked_member
data:
  memberId: "..."  # bắt buộc - memberId
  groupId: "..."   # bắt buộc - groupId
  confirm: false   # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `memberId` | memberId | có | member id(s) (string \| string[]) |
| `groupId` | groupId | có | group id (string) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="analyse_group"></a>
#### analyseGroup — `zalo_call.analyse_group`

analyseGroup — Lấy dữ liệu phân tích/thống kê của nhóm qua /api/group/analyse (command 12407)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.analyse_group
data:
  groupId: "..."  # bắt buộc - groupId
  params: {}      # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | ID của nhóm (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="check_quota_community_member"></a>
#### checkQuotaCommunityMember — `zalo_call.check_quota_community_member`

checkQuotaCommunityMember — Kiểm tra điều kiện/hạn mức thành viên Cộng đồng đối với một thành viên cụ thể trong nhóm (command 12182)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.check_quota_community_member
data:
  groupId: "..."  # bắt buộc - groupId
  uid: "..."      # bắt buộc - uid
  params: {}      # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | ID của nhóm (string) |
| `uid` | uid | có | UID của thành viên cần kiểm tra (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="delete_group_invite_box"></a>
#### deleteGroupInviteBox — `zalo_call.delete_group_invite_box`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

deleteGroupInviteBox — Xóa lời mời tham gia nhóm trong hộp thư lời mời nhóm. (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.delete_group_invite_box
data:
  groupId: "..."            # bắt buộc - groupId
  blockFutureInvite: "..."  # tuỳ chọn - blockFutureInvite
  params: {}                # bắt buộc - params
  confirm: false            # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | - The group id (string \| string[]) |
| `blockFutureInvite` | blockFutureInvite | không | - Whether to block future invites from this group (boolean) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="get_e2ee_group_list"></a>
#### getE2eeGroupList — `zalo_call.get_e2ee_group_list`

getE2eeGroupList — Lấy danh sách các nhóm đang bật mã hóa đầu cuối E2EE (command 12146)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_e2ee_group_list
```

---

<a id="get_extra_group_info"></a>
#### getExtraGroupInfo — `zalo_call.get_extra_group_info`

getExtraGroupInfo — Lấy ngữ cảnh và vai trò mở rộng của người dùng đối với nhiều nhóm (command 12607)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_extra_group_info
data:
  groupIds: "..."  # bắt buộc - groupIds
  params: {}       # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupIds` | groupIds | có | Mảng ID các nhóm cần truy vấn (string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_group_blocked_member"></a>
#### getGroupBlockedMember — `zalo_call.get_group_blocked_member`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

getGroupBlockedMember — Lấy danh sách các tài khoản đang bị chặn khỏi nhóm. (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_group_blocked_member
data:
  payload: "..."  # bắt buộc - payload
  groupId: "..."  # bắt buộc - groupId
  params: {}      # bắt buộc - params
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `payload` | payload | có | payload (GetGroupBlockedMemberPayload) |
| `groupId` | groupId | có | group id (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="get_group_cloud_message_jump"></a>
#### getGroupCloudMessageJump — `zalo_call.get_group_cloud_message_jump`

getGroupCloudMessageJump — Nhảy tới vị trí một tin nhắn nhóm cụ thể trên Zalo Cloud Message và lấy ngữ cảnh xung quanh (command 12508)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_group_cloud_message_jump
data:
  groupId: "..."      # bắt buộc - groupId
  globalMsgId: "..."  # bắt buộc - globalMsgId
  count: 50           # tuỳ chọn - count
  msgJump: "..."      # tuỳ chọn - msgJump
  msgIds: "..."       # tuỳ chọn - msgIds
  params: {}          # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | ID nhóm (string) |
| `globalMsgId` | globalMsgId | có | ID tin nhắn toàn cục cần nhảy tới (string \| number) |
| `count` | count | không | Số lượng tin nhắn ngữ cảnh cần tải (mặc định `20`) (number) |
| `msgJump` | msgJump | không | Cờ nhảy tin nhắn (mặc định `1`) (number) |
| `msgIds` | msgIds | không | Danh sách msgId bổ sung (mặc định `[]`) (Array<string \| number>) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_group_cloud_message_path"></a>
#### getGroupCloudMessagePath — `zalo_call.get_group_cloud_message_path`

getGroupCloudMessagePath — Lấy chuỗi tin nhắn nhóm theo đường dẫn nhảy tới một tin nhắn cụ thể (globalMsgId / rGlobalMsgId) qua /api/cm/getpath (command 12504)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_group_cloud_message_path
data:
  groupId: "..."       # bắt buộc - groupId
  globalMsgId: "..."   # bắt buộc - globalMsgId
  count: 50            # tuỳ chọn - count
  reverse: "..."       # tuỳ chọn - reverse
  rGlobalMsgId: "..."  # tuỳ chọn - rGlobalMsgId
  rOwnerId: "..."      # tuỳ chọn - rOwnerId
  rClientMsgId: "..."  # tuỳ chọn - rClientMsgId
  params: {}           # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | groupId (string) |
| `globalMsgId` | globalMsgId | có | globalMsgId (string \| number) |
| `count` | count | không | count (number) |
| `reverse` | reverse | không | reverse (number \| boolean) |
| `rGlobalMsgId` | rGlobalMsgId | không | rGlobalMsgId (string \| number) |
| `rOwnerId` | rOwnerId | không | rOwnerId (string) |
| `rClientMsgId` | rClientMsgId | không | rClientMsgId (string \| number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_group_info_v2"></a>
#### getGroupInfoV2 — `zalo_call.get_group_info_v2`

getGroupInfoV2 — Lấy thông tin nhóm và danh sách thành viên theo trang qua /api/group/getgi/v2 hoặc /api/group/getgi (command 11162) (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_group_info_v2
```

---

<a id="get_group_invite_box_info"></a>
#### getGroupInviteBoxInfo — `zalo_call.get_group_invite_box_info`

getGroupInviteBoxInfo — Lấy thông tin chi tiết của một lời mời vào nhóm cụ thể.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_group_invite_box_info
data:
  groupId: "..."  # bắt buộc - groupId
  mpage: "..."    # tuỳ chọn - mpage
  mcount: "..."   # tuỳ chọn - mcount
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | groupId (string) |
| `mpage` | mpage | không | mpage (number) |
| `mcount` | mcount | không | mcount (number) |

---

<a id="get_group_invite_box_list"></a>
#### getGroupInviteBoxList — `zalo_call.get_group_invite_box_list`

getGroupInviteBoxList — Lấy danh sách tất cả lời mời tham gia nhóm đang chờ trong hộp thư.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_group_invite_box_list
data:
  mpage: "..."       # tuỳ chọn - mpage
  page: "1"          # tuỳ chọn - page
  invPerPage: "..."  # tuỳ chọn - invPerPage
  mcount: "..."      # tuỳ chọn - mcount
  params: {}         # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `mpage` | mpage | không | mpage (number) |
| `page` | page | không | page (number) |
| `invPerPage` | invPerPage | không | invPerPage (number) |
| `mcount` | mcount | không | mcount (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_group_link_info"></a>
#### getGroupLinkInfo — `zalo_call.get_group_link_info`

getGroupLinkInfo — Tra cứu thông tin nhóm và danh sách thành viên theo trang từ đường dẫn nhóm công khai (https://zalo.me/g/...).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_group_link_info
data:
  link: "https://zalo.me/g/abcxyz"  # bắt buộc - link
  memberPage: "..."                 # tuỳ chọn - memberPage
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `link` | link | có | link (string) |
| `memberPage` | memberPage | không | Default: 1 (number) |

---

<a id="get_group_list_v3"></a>
#### getGroupListV3 — `zalo_call.get_group_list_v3`

getGroupListV3 — Lấy danh sách nhóm theo trang kèm thông tin thành viên đại diện (currentMems) và gợi ý nhóm (suggestGroup) qua /api/group/getlg/v3 (command 11161)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_group_list_v3
data:
  pageOrOptions: "..."  # tuỳ chọn - pageOrOptions
  params: {}            # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `pageOrOptions` | pageOrOptions | không | Số trang (mặc định: `1`) hoặc cấu hình `GetGroupListV3Options` (number \| GetGroupListV3Options) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_group_members_info"></a>
#### getGroupMembersInfo — `zalo_call.get_group_members_info`

getGroupMembersInfo — Giải mã hàng loạt thông tin hồ sơ thành viên (displayName, zaloName, avatar, globalId) từ danh sách UID qua /api/social/group/members.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_group_members_info
data:
  memberId: "..."  # bắt buộc - memberId
  params: {}       # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `memberId` | memberId | có | member id or array of member ids (string \| string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_group_message_status"></a>
#### getGroupMessageStatus — `zalo_call.get_group_message_status`

getGroupMessageStatus — Truy vấn trạng thái Đã nhận (deliver) và Đã xem (seen) tin nhắn của danh sách thành viên trong nhóm (command 12017)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_group_message_status
data:
  groupIdOrItems: "..."  # bắt buộc - groupIdOrItems
  memberIds: "..."       # tuỳ chọn - memberIds
  params: {}             # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupIdOrItems` | groupIdOrItems | có | ID nhóm (hoặc mảng cấu hình `{ tId, ids }`) (string \| GetGroupMessageStatusQueryItem[]) |
| `memberIds` | memberIds | không | Danh sách UID thành viên cần kiểm tra (khi tham số đầu là `groupId`) (string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_multi_group_cloud_messages"></a>
#### getMultiGroupCloudMessages — `zalo_call.get_multi_group_cloud_messages`

getMultiGroupCloudMessages — Đồng bộ nhanh tin nhắn Cloud của nhiều nhóm cùng lúc theo danh sách groupIds (command 12503 - syncCloudMsgFirstLogin)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_multi_group_cloud_messages
data:
  groupIds: "..."  # bắt buộc - groupIds
  nretry: "..."    # tuỳ chọn - nretry
  params: {}       # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupIds` | groupIds | có | Danh sách ID nhóm cần tải tin nhắn Cloud (string[]) |
| `nretry` | nretry | không | Số lần thử lại (mặc định: `0`) (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_pending_group_members"></a>
#### getPendingGroupMembers — `zalo_call.get_pending_group_members`

getPendingGroupMembers — Lấy danh sách các yêu cầu xin vào nhóm đang chờ Quản trị viên phê duyệt.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_pending_group_members
data:
  groupId: "..."  # bắt buộc - groupId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | - The id of the group to get the pending members (string) |

---

<a id="get_quota_community"></a>
#### getQuotaCommunity — `zalo_call.get_quota_community`

getQuotaCommunity — Kiểm tra hạn mức nâng cấp nhóm lên Cộng đồng của tài khoản (command 12181)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_quota_community
data:
  groupId: "..."  # tuỳ chọn - groupId
  language: "vi"  # tuỳ chọn - language
  params: {}      # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | không | (Tùy chọn) ID của nhóm cần kiểm tra (string \| null) |
| `language` | language | không | Ngôn ngữ thông báo (mặc định: `"vi"`) (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_related_friend_group"></a>
#### getRelatedFriendGroup — `zalo_call.get_related_friend_group`

getRelatedFriendGroup — Kiểm tra danh sách các nhóm chung giữa tài khoản hiện tại và danh sách UID truyền vào qua /api/friend/group/related.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_related_friend_group
data:
  friendId: "..."  # bắt buộc - friendId
  params: {}       # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `friendId` | friendId | có | friend ids (string \| string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="invite_user_to_groups"></a>
#### inviteUserToGroups — `zalo_call.invite_user_to_groups`

inviteUserToGroups — Gửi lời mời tham gia một hoặc nhiều nhóm tới người dùng.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.invite_user_to_groups
data:
  userId: "..."   # bắt buộc - userId
  groupId: "..."  # bắt buộc - groupId
  params: {}      # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `userId` | userId | có | userId (string) |
| `groupId` | groupId | có | group ID(s) (string \| string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="join_group_invite_box"></a>
#### joinGroupInviteBox — `zalo_call.join_group_invite_box`

joinGroupInviteBox — Chấp nhận lời mời tham gia nhóm từ hộp thư lời mời.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.join_group_invite_box
data:
  groupId: "..."  # bắt buộc - groupId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | - The group id (string) |

---

<a id="remove_group_blocked_member"></a>
#### removeGroupBlockedMember — `zalo_call.remove_group_blocked_member`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

removeGroupBlockedMember — Gỡ chặn (Unblock) cho người dùng khỏi danh sách chặn của nhóm. (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_group_blocked_member
data:
  memberId: "..."  # bắt buộc - memberId
  groupId: "..."   # bắt buộc - groupId
  confirm: false   # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `memberId` | memberId | có | member id(s) (string \| string[]) |
| `groupId` | groupId | có | group id (string) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="remove_group_topic"></a>
#### removeGroupTopic — `zalo_call.remove_group_topic`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

removeGroupTopic — Xóa chủ đề đang ghim trên đầu nhóm (command 11829) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_group_topic
data:
  groupId: "..."  # bắt buộc - groupId
  params: {}      # bắt buộc - params
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | ID nhóm (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="remove_user_from_groups"></a>
#### removeUserFromGroups — `zalo_call.remove_user_from_groups`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

removeUserFromGroups — Xóa một thành viên khỏi nhiều nhóm cùng lúc (command 12606) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_user_from_groups
data:
  groupIds: "..."        # bắt buộc - groupIds
  memberId: "..."        # bắt buộc - memberId
  srcInteraction: "..."  # tuỳ chọn - srcInteraction
  params: {}             # bắt buộc - params
  confirm: false         # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupIds` | groupIds | có | Danh sách ID nhóm (string \| string[]) |
| `memberId` | memberId | có | ID thành viên cần xóa khỏi các nhóm (string) |
| `srcInteraction` | srcInteraction | không | Nguồn tương tác (mặc định `2`) (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="review_pending_member_request"></a>
#### reviewPendingMemberRequest — `zalo_call.review_pending_member_request`

reviewPendingMemberRequest — Phê duyệt (Chấp nhận hoặc Từ chối) yêu cầu xin tham gia nhóm của thành viên mới.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.review_pending_member_request
data:
  payload: "..."  # bắt buộc - payload
  groupId: "..."  # bắt buộc - groupId
  params: {}      # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `payload` | payload | có | - The payload containing data to review the pending member(s) request (ReviewPendingMemberRequestPayload) |
| `groupId` | groupId | có | - The id of the group to review the pending member(s) request (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="update_group_settings"></a>
#### updateGroupSettings — `zalo_call.update_group_settings`

updateGroupSettings — Cập nhật các thiết lập quyền hạn của nhóm (ẩn thành viên lockViewMember, duyệt thành viên joinAppr, khóa nhắn tin lockSendMsg...).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_group_settings
data:
  options: "{\"voice\": \"nova\"}"  # bắt buộc - options
  groupId: "..."                    # bắt buộc - groupId
  params: {}                        # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `options` | options | có | Options (UpdateGroupSettingsOptions) |
| `groupId` | groupId | có | Group ID (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="upgrade_group_to_community"></a>
#### upgradeGroupToCommunity — `zalo_call.upgrade_group_to_community`

upgradeGroupToCommunity — Nâng cấp nhóm thường lên Cộng đồng (Community - tối đa 1000 thành viên).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.upgrade_group_to_community
data:
  groupId: "..."  # bắt buộc - groupId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | Group ID upgrade (string) |

---

## Bạn bè (nâng cao)

<a id="clear_unread_friend_requests"></a>
#### clearUnreadFriendRequests — `zalo_call.clear_unread_friend_requests`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

clearUnreadFriendRequests — Đánh dấu đã xem danh sách lời mời kết bạn chưa đọc (command 12232) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.clear_unread_friend_requests
data:
  uidsSeen: "..."  # tuỳ chọn - uidsSeen
  confirm: false   # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `uidsSeen` | uidsSeen | không | Danh sách UID đã xem lời mời kết bạn (mặc định `[]`) (string[]) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="find_user_by_username"></a>
#### findUserByUsername — `zalo_call.find_user_by_username`

findUserByUsername — Tìm kiếm thông tin tài khoản Zalo thông qua Username.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.find_user_by_username
data:
  username: "..."    # bắt buộc - username
  avatarSize: "..."  # tuỳ chọn - avatarSize
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `username` | username | có | username for find (string) |
| `avatarSize` | avatarSize | không | Avatar size (default: AvatarSize.Large) (AvatarSize) |

---

<a id="get_alias_list"></a>
#### getAliasList — `zalo_call.get_alias_list`

getAliasList — Lấy danh sách toàn bộ tên gợi nhớ (Alias) đã đặt cho bạn bè.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_alias_list
data:
  count: 50  # tuỳ chọn - count
  page: "1"  # tuỳ chọn - page
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `count` | count | không | Page size (default: 100) (number) |
| `page` | page | không | Page number (default: 1) (number) |

---

<a id="get_alias_list_v2"></a>
#### getAliasListV2 — `zalo_call.get_alias_list_v2`

getAliasListV2 — Lấy danh sách tên gợi nhớ (Alias) của bạn bè chuẩn V2 có hỗ trợ phân trang (command 12205)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_alias_list_v2
data:
  page: "1"  # tuỳ chọn - page
  count: 50  # tuỳ chọn - count
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `page` | page | không | Trang cần lấy (mặc định: 1) (number) |
| `count` | count | không | Số lượng mục mỗi trang (mặc định: 100) (number) |

---

<a id="get_block_friends"></a>
#### getBlockFriends — `zalo_call.get_block_friends`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

getBlockFriends — Lấy danh sách người dùng đang bị chặn chuẩn V2 (command 11429) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_block_friends
data:
  page: "1"          # tuỳ chọn - page
  count: 50          # tuỳ chọn - count
  avatarSize: "..."  # tuỳ chọn - avatarSize
  confirm: false     # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `page` | page | không | Trang cần lấy (mặc định: 1) (number) |
| `count` | count | không | Số lượng mỗi trang (mặc định: 50) (number) |
| `avatarSize` | avatarSize | không | Kích thước ảnh đại diện (mặc định: 120) (number) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="get_close_friends"></a>
#### getCloseFriends — `zalo_call.get_close_friends`

getCloseFriends — Lấy danh sách bạn thân (Close Friends).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_close_friends
```

---

<a id="get_extra_friend_info"></a>
#### getExtraFriendInfo — `zalo_call.get_extra_friend_info`

getExtraFriendInfo — Lấy ngữ cảnh và vai trò mở rộng (ví dụ role: ["boss"]) của danh sách bạn bè (command 11442)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_extra_friend_info
data:
  friendIds: "..."  # bắt buộc - friendIds
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `friendIds` | friendIds | có | Mảng UID cần truy vấn (string[]) |

---

<a id="get_friend_board_list"></a>
#### getFriendBoardList — `zalo_call.get_friend_board_list`

getFriendBoardList — Lấy thông tin bảng tin chung với một người bạn.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_friend_board_list
data:
  conversationId: "..."  # bắt buộc - conversationId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `conversationId` | conversationId | có | conversation id (string) |

---

<a id="get_friend_onlines"></a>
#### getFriendOnlines — `zalo_call.get_friend_onlines`

getFriendOnlines — Lấy danh sách bạn bè đang trực tuyến (Online) kèm trạng thái thiết bị.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_friend_onlines
```

---

<a id="get_friend_recommendations"></a>
#### getFriendRecommendations — `zalo_call.get_friend_recommendations`

getFriendRecommendations — Lấy danh sách gợi ý kết bạn và lời mời kết bạn đã nhận.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_friend_recommendations
```

---

<a id="get_friend_request_status"></a>
#### getFriendRequestStatus — `zalo_call.get_friend_request_status`

getFriendRequestStatus — Kiểm tra trạng thái quan hệ bạn bè và lời mời kết bạn với một UID.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_friend_request_status
data:
  friendId: "..."  # bắt buộc - friendId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `friendId` | friendId | có | friend id (string) |

---

<a id="get_friends_active_p_c_web"></a>
#### getFriendsActivePCWeb — `zalo_call.get_friends_active_p_c_web`

getFriendsActivePCWeb — Lấy danh sách bạn bè đang hoạt động trên Zalo PC / Web qua /api/social/friend/active-pcweb (command 12072)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_friends_active_p_c_web
```

---

<a id="get_friends_emoji_status"></a>
#### getFriendsEmojiStatus — `zalo_call.get_friends_emoji_status`

getFriendsEmojiStatus — Lấy danh sách trạng thái Emoji (Emoji Status) hiện tại của bạn bè (command 16301)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_friends_emoji_status
data:
  version: "..."           # tuỳ chọn - version
  fromUid: "..."           # tuỳ chọn - fromUid
  maxEmojiStatusId: "..."  # tuỳ chọn - maxEmojiStatusId
  page: "1"                # tuỳ chọn - page
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `version` | version | không | version (number) |
| `fromUid` | fromUid | không | fromUid (string) |
| `maxEmojiStatusId` | maxEmojiStatusId | không | maxEmojiStatusId (string \| number) |
| `page` | page | không | page (number) |

---

<a id="get_last_read_contact_tab"></a>
#### getLastReadContactTab — `zalo_call.get_last_read_contact_tab`

getLastReadContactTab — Lấy dấu thời gian lần cuối đọc tab Danh bạ (command 12230)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_last_read_contact_tab
```

---

<a id="get_multi_user_q_r_codes"></a>
#### getMultiUserQRCodes — `zalo_call.get_multi_user_q_r_codes`

getMultiUserQRCodes — Lấy mã QR cá nhân của một hoặc nhiều người dùng (command 12128)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_multi_user_q_r_codes
data:
  fids: "..."  # bắt buộc - fids
  params: {}   # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `fids` | fids | có | ID hoặc danh sách ID người dùng (string \| string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_multi_users_by_phones"></a>
#### getMultiUsersByPhones — `zalo_call.get_multi_users_by_phones`

getMultiUsersByPhones — Tra cứu hàng loạt thông tin tài khoản Zalo từ danh sách nhiều số điện thoại cùng lúc.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_multi_users_by_phones
data:
  phoneNumbers: "..."  # bắt buộc - phoneNumbers
  avatarSize: "..."    # tuỳ chọn - avatarSize
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `phoneNumbers` | phoneNumbers | có | Phone number(s) (string \| string[]) |
| `avatarSize` | avatarSize | không | Avatar size (default: AvatarSize.Large) (AvatarSize) |

---

<a id="get_phonebook_v2"></a>
#### getPhonebookV2 — `zalo_call.get_phonebook_v2`

getPhonebookV2 — Lấy danh bạ bạn bè đồng bộ từ số điện thoại chuẩn V2 (command 12428)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_phonebook_v2
data:
  phonebookVersion: "..."  # tuỳ chọn - phonebookVersion
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `phonebookVersion` | phonebookVersion | không | Phiên bản danh bạ (mặc định: 0 để lấy toàn bộ) (number) |

---

<a id="read_contact_tab"></a>
#### readContactTab — `zalo_call.read_contact_tab`

readContactTab — Đánh dấu đã đọc tab Danh bạ (command 12231)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.read_contact_tab
data:
  ts: "..."  # tuỳ chọn - ts
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `ts` | ts | không | Dấu thời gian (mặc định: `Date.now()`) (number) |

---

<a id="remove_friend_recommendation"></a>
#### removeFriendRecommendation — `zalo_call.remove_friend_recommendation`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

removeFriendRecommendation — Xóa một gợi ý kết bạn khỏi danh sách đề xuất (command 11432) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_friend_recommendation
data:
  uid: "..."      # bắt buộc - uid
  src: "..."      # tuỳ chọn - src
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `uid` | uid | có | ID người dùng cần ẩn khỏi gợi ý (string) |
| `src` | src | không | Nguồn gợi ý (mặc định `0`) (number) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="remove_friend_recommendation_v2"></a>
#### removeFriendRecommendationV2 — `zalo_call.remove_friend_recommendation_v2`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

removeFriendRecommendationV2 — Xóa một gợi ý kết bạn khỏi danh sách đề xuất V2 (command 11438) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_friend_recommendation_v2
data:
  uid: "..."      # bắt buộc - uid
  src: "..."      # tuỳ chọn - src
  type: 0         # tuỳ chọn - type
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `uid` | uid | có | ID người dùng cần ẩn khỏi gợi ý (string) |
| `src` | src | không | Nguồn gợi ý (mặc định `0`) (number) |
| `type` | type | không | Loại gợi ý (mặc định `0`) (number) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

**Các lựa chọn:**

- **type** (`type`)
  - `0`: loại gợi ý mặc định (mã 0 của Zalo)
  - `1`: loại gợi ý mã 1 của Zalo (app chưa chú giải nghĩa)

---

<a id="update_close_friend"></a>
#### updateCloseFriend — `zalo_call.update_close_friend`

updateCloseFriend — Thêm hoặc xóa người dùng khỏi danh sách Bạn thân (command 11421)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_close_friend
data:
  fids: "..."    # bắt buộc - fids
  action: "..."  # tuỳ chọn - action
  params: {}     # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `fids` | fids | có | ID hoặc danh sách ID người dùng (string \| string[]) |
| `action` | action | không | Hành động (`1` = Thêm bạn thân, `0` = Xóa bạn thân) (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="verify_friend"></a>
#### verifyFriend — `zalo_call.verify_friend`

verifyFriend — Kiểm tra và xác thực danh sách bạn bè qua /api/social/friend/verify (command 11138)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.verify_friend
data:
  friendIds: "..."                  # bắt buộc - friendIds
  options: "{\"voice\": \"nova\"}"  # tuỳ chọn - options
  params: {}                        # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `friendIds` | friendIds | có | Danh sách UID bạn bè cần xác thực (string \| string[]) |
| `options` | options | không | Tùy chọn truy vấn (VerifyFriendOptions) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

## Hồ sơ (nâng cao)

<a id="delete_avatar"></a>
#### deleteAvatar — `zalo_call.delete_avatar`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

deleteAvatar — Xóa một hoặc nhiều ảnh đại diện cũ trong kho ảnh đại diện. (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.delete_avatar
data:
  photoId: "..."  # bắt buộc - photoId
  params: {}      # bắt buộc - params
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `photoId` | photoId | có | avatar photo ID(s) to delete - can be a single string or array of strings (string \| string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="disable_limit_search_phone_reminder"></a>
#### disableLimitSearchPhoneReminder — `zalo_call.disable_limit_search_phone_reminder`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

disableLimitSearchPhoneReminder — Tắt thông báo nhắc nhở giới hạn tìm kiếm số điện thoại (command 12131) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.disable_limit_search_phone_reminder
data:
  uid: "..."      # tuỳ chọn - uid
  params: {}      # bắt buộc - params
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `uid` | uid | không | ID người dùng (mặc định là `ctx.uid`) (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="fetch_account_info"></a>
#### fetchAccountInfo — `zalo_call.fetch_account_info`

fetchAccountInfo — API fetchAccountInfo thuộc phân hệ profile.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.fetch_account_info
```

---

<a id="get_avatar_url_profile"></a>
#### getAvatarUrlProfile — `zalo_call.get_avatar_url_profile`

getAvatarUrlProfile — Lấy đường dẫn ảnh đại diện của danh sách hồ sơ người dùng.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_avatar_url_profile
data:
  friendIds: "..."   # bắt buộc - friendIds
  avatarSize: "..."  # tuỳ chọn - avatarSize
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `friendIds` | friendIds | có | friendIds (string \| string[]) |
| `avatarSize` | avatarSize | không | Avatar size (default: AvatarSize.Large) (AvatarSize) |

---

<a id="get_emoji_status_config"></a>
#### getEmojiStatusConfig — `zalo_call.get_emoji_status_config`

getEmojiStatusConfig — Lấy cấu hình và danh sách bộ biểu tượng Trạng thái Emoji (Emoji Status - command 16300)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_emoji_status_config
data:
  version: "..."  # tuỳ chọn - version
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `version` | version | không | Phiên bản bộ nhớ đệm (mặc định: 0 để lấy đầy đủ danh sách) (number) |

---

<a id="get_enterprise_profiles"></a>
#### getEnterpriseProfiles — `zalo_call.get_enterprise_profiles`

getEnterpriseProfiles — Lấy thông tin hồ sơ doanh nghiệp (Zalo Enterprise) của một hoặc nhiều tài khoản (command 12193)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_enterprise_profiles
data:
  uids: "..."  # bắt buộc - uids
  params: {}   # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `uids` | uids | có | ID hoặc danh sách ID người dùng (string \| string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_full_avatar"></a>
#### getFullAvatar — `zalo_call.get_full_avatar`

getFullAvatar — Lấy ảnh đại diện kích thước gốc (Full HD) của một người dùng theo UID.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_full_avatar
data:
  friendId: "..."  # bắt buộc - friendId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `friendId` | friendId | có | friend id (string) |

---

<a id="get_mini_profile"></a>
#### getMiniProfile — `zalo_call.get_mini_profile`

getMiniProfile — Lấy nhanh thông tin hồ sơ rút gọn (Avatar, Global ID, gói Biz) của danh sách người dùng (command 12134)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_mini_profile
data:
  friendIds: "..."   # bắt buộc - friendIds
  avatarSize: "..."  # tuỳ chọn - avatarSize
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `friendIds` | friendIds | có | Mảng UID cần lấy thông tin (string[]) |
| `avatarSize` | avatarSize | không | Kích thước ảnh đại diện (mặc định: 120) (number) |

---

<a id="get_profile_extra"></a>
#### getProfileExtra — `zalo_call.get_profile_extra`

getProfileExtra — Lấy thông tin mở rộng của hồ sơ cá nhân (command 11864)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_profile_extra
data:
  profileId: "..."  # tuỳ chọn - profileId
  params: {}        # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `profileId` | profileId | không | ID người dùng (mặc định là `ctx.uid`) (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_profile_rank"></a>
#### getProfileRank — `zalo_call.get_profile_rank`

getProfileRank — Lấy hạng tài khoản Zalo của một người dùng (ví dụ "WHITE", "GOLD" - command 12012)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_profile_rank
data:
  profileId: "..."  # tuỳ chọn - profileId
  params: {}        # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `profileId` | profileId | không | UID của người dùng cần kiểm tra (mặc định: UID của tài khoản đang đăng nhập) (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_profile_verification_status"></a>
#### getProfileVerificationStatus — `zalo_call.get_profile_verification_status`

getProfileVerificationStatus — Kiểm tra trạng thái xác thực định danh (eKYC) của tài khoản Zalo (command 12150)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_profile_verification_status
```

---

<a id="push_profile_verification_message"></a>
#### pushProfileVerificationMessage — `zalo_call.push_profile_verification_message`

pushProfileVerificationMessage — Yêu cầu đẩy tin nhắn hướng dẫn xác thực tài khoản (eKYC) từ Official Account (command 12151)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.push_profile_verification_message
data:
  uid: "..."        # tuỳ chọn - uid
  groupName: "..."  # tuỳ chọn - groupName
  type: 0           # tuỳ chọn - type
  params: {}        # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `uid` | uid | không | uid (string) |
| `groupName` | groupName | không | groupName (string) |
| `type` | type | không | type (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

**Các lựa chọn:**

- **type** (`type`)
  - `0`: mã 0 của Zalo (app chưa chú giải nghĩa; giữ mặc định nếu không chắc)
  - `1`: mã 1 của Zalo (app chưa chú giải nghĩa; giữ mặc định nếu không chắc)

---

<a id="register_trial_biz_account"></a>
#### registerTrialBizAccount — `zalo_call.register_trial_biz_account`

registerTrialBizAccount — Đăng ký dùng thử gói Zalo Business V2 cho tài khoản (command 12152)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.register_trial_biz_account
data:
  uid: "..."  # tuỳ chọn - uid
  params: {}  # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `uid` | uid | không | ID người dùng (mặc định là `ctx.uid`) (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="reuse_avatar"></a>
#### reuseAvatar — `zalo_call.reuse_avatar`

reuseAvatar — Sử dụng lại một ảnh đại diện cũ từ kho lịch sử ảnh đại diện.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.reuse_avatar
data:
  photoId: "..."  # bắt buộc - photoId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `photoId` | photoId | có | photo id from getAvatarList api (string) |

---

<a id="update_profile_bio"></a>
#### updateProfileBio — `zalo_call.update_profile_bio`

updateProfileBio — Cập nhật dòng tiểu sử (Status / Bio) trên trang cá nhân.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_profile_bio
data:
  status: 1  # bắt buộc - status
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `status` | status | có | status for update bio (string) |

**Các lựa chọn:**

- **status** (`status`)
  - `1`: mã trạng thái 1 của Zalo (app chưa chú giải nghĩa)
  - `0`: mã trạng thái 0 của Zalo (app chưa chú giải nghĩa)

---

<a id="update_profile_mode"></a>
#### updateProfileMode — `zalo_call.update_profile_mode`

updateProfileMode — Cập nhật chế độ hồ sơ người dùng (command 11865)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_profile_mode
data:
  mode: "..."  # bắt buộc - mode
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `mode` | mode | có | Chế độ hồ sơ cần đặt (number) |

---

## Đồng bộ (nâng cao)

<a id="cancel_pull_mobile"></a>
#### cancelPullMobile — `zalo_call.cancel_pull_mobile`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

cancelPullMobile — Huỷ yêu cầu đồng bộ tin nhắn từ điện thoại đang chờ (cancel_pull_mobile_msg, command 12700). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet)) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.cancel_pull_mobile
data:
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="delete_mobile_msg_snapshot"></a>
#### deleteMobileMsgSnapshot — `zalo_call.delete_mobile_msg_snapshot`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

deleteMobileMsgSnapshot — Xóa bản chụp nhanh (snapshot) dữ liệu đồng bộ tin nhắn từ thiết bị di động sau khi hoàn tất (command 12003) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.delete_mobile_msg_snapshot
data:
  publicKey: "..."  # bắt buộc - publicKey
  confirm: false    # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `publicKey` | publicKey | có | Khóa công khai RSA SPKI DER Base64 của phiên đồng bộ (string) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="download_transfer_sync"></a>
#### downloadTransferSync — `zalo_call.download_transfer_sync`

downloadTransferSync — Tải khối dữ liệu snapshot đồng bộ tin nhắn từ máy chủ transfersync.zaloapp.com (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.download_transfer_sync
```

---

<a id="get_backup_msg_info"></a>
#### getBackupMsgInfo — `zalo_call.get_backup_msg_info`

getBackupMsgInfo — Lấy thông tin bản sao lưu tin nhắn hiện có trên máy chủ (command 12096)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_backup_msg_info
data:
  nretry: "..."  # tuỳ chọn - nretry
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `nretry` | nretry | không | Số lần thử lại (mặc định `0`) (number) |

---

<a id="get_cross_db_info"></a>
#### getCrossDbInfo — `zalo_call.get_cross_db_info`

getCrossDbInfo — Lấy thông tin cơ sở dữ liệu chéo (Cross-DB) phục vụ đồng bộ dữ liệu sang máy tính (command 12412)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_cross_db_info
data:
  syncSession: "..."  # tuỳ chọn - syncSession
  pcName: "..."       # tuỳ chọn - pcName
  nretry: "..."       # tuỳ chọn - nretry
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `syncSession` | syncSession | không | syncSession (string) |
| `pcName` | pcName | không | pcName (string) |
| `nretry` | nretry | không | nretry (number) |

---

<a id="get_sync_data"></a>
#### getSyncData — `zalo_call.get_sync_data`

getSyncData — Tải xuống file sao lưu tin nhắn từ sự kiện syncmsg_info (.db.crypt, định dạng ZDB4.0) và lưu ra ổ đĩa hoặc trả về ReadableStream. (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_sync_data
```

---

<a id="pull_mobile"></a>
#### pullMobile — `zalo_call.pull_mobile`

pullMobile — Yêu cầu thiết bị di động Zalo đóng gói và tải lên bản sao lưu tin nhắn (pull_mobile_msg, command 12000). Sự kiện tiến trình (user_confirm, syncmsg_info, transfer_error) sẽ được đẩy về qua api.listener.on("sync_event"). (chưa tự

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.pull_mobile
```

---

<a id="request_sync_from_phone"></a>
#### requestSyncFromPhone — `zalo_call.request_sync_from_phone`

requestSyncFromPhone — Phát tín hiệu yêu cầu đồng bộ tin nhắn từ ứng dụng Zalo trên điện thoại (pull_mobile_msg, command 12000). Tự động sinh cặp khoá RSA 2048-bit (nếu chưa truyền vào) và gọi api.pullMobile(...). Điện thoại của người dùng

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.request_sync_from_phone
```

---

<a id="submit_sync_media_actions"></a>
#### submitSyncMediaActions — `zalo_call.submit_sync_media_actions`

submitSyncMediaActions — Gửi danh sách hành động đồng bộ hóa tệp đa phương tiện lên máy chủ (command 16213)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.submit_sync_media_actions
data:
  syncList: "..."  # bắt buộc - syncList
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `syncList` | syncList | có | Danh sách hành động đồng bộ Media (unknown[]) |

---

<a id="upload_backup_chunk"></a>
#### uploadBackupChunk — `zalo_call.upload_backup_chunk`

uploadBackupChunk — Tải lên gói dữ liệu phân mảnh (chunk) sao lưu tin nhắn từ máy tính sang điện thoại (command 13538)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.upload_backup_chunk
data:
  formData: "..."  # bắt buộc - formData
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `formData` | formData | có | Dữ liệu `FormData` hoặc `BodyInit` chứa phân mảnh sao lưu (BodyInit \| Buffer \| Uint8Array) |

---

## Zalo Cloud

<a id="ack_cloud_onboarding"></a>
#### ackCloudOnboarding — `zalo_call.ack_cloud_onboarding`

ackCloudOnboarding — Xác nhận hoàn tất bước khởi tạo (Onboarding ACK V1) trên ZCloud (command 12746) (chưa tự động: goi 0 request (nhieu buoc hoac khong goi))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.ack_cloud_onboarding
```

---

<a id="get_cloud_download_urls"></a>
#### getCloudDownloadUrls — `zalo_call.get_cloud_download_urls`

getCloudDownloadUrls — Lấy danh sách đường dẫn tải xuống các tệp Media lưu trữ trên ZCloud theo noiseIds (command 12743) (chưa tự động: goi 0 request (nhieu buoc hoac khong goi))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_cloud_download_urls
```

---

<a id="get_cloud_info"></a>
#### getCloudInfo — `zalo_call.get_cloud_info`

getCloudInfo — Lấy thông tin gói thuê bao Zalo Cloud (command 12754) (chưa tự động: goi 0 request (nhieu buoc hoac khong goi))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_cloud_info
```

---

<a id="get_cloud_settings"></a>
#### getCloudSettings — `zalo_call.get_cloud_settings`

getCloudSettings — Lấy cấu hình giới hạn tệp và cài đặt ZCloud của tài khoản (command 12756) (chưa tự động: goi 0 request (nhieu buoc hoac khong goi))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_cloud_settings
```

---

<a id="get_cloud_upload_url"></a>
#### getCloudUploadUrl — `zalo_call.get_cloud_upload_url`

getCloudUploadUrl — Lấy đường dẫn tải lên tệp di trú lên ZCloud (command 12752) (chưa tự động: goi 0 request (nhieu buoc hoac khong goi))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_cloud_upload_url
```

---

<a id="get_cloud_viewer_key"></a>
#### getCloudViewerKey — `zalo_call.get_cloud_viewer_key`

getCloudViewerKey — Lấy cặp khóa phiên (viewer_key và khóa giải mã AES-256 enk) cho hệ thống ZCloud / MyCloud (command 12741). Tự động cache trong bộ nhớ ctx.zcloudViewerKeyCache (TTL 15 phút) để tối ưu hiệu năng khi gọi liên tiếp. (chưa tự

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_cloud_viewer_key
```

---

<a id="get_family_profile"></a>
#### getFamilyProfile — `zalo_call.get_family_profile`

getFamilyProfile — Lấy thông tin nhóm gia đình ZFamily (command 12757) (chưa tự động: goi 0 request (nhieu buoc hoac khong goi))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_family_profile
```

---

<a id="get_family_usage"></a>
#### getFamilyUsage — `zalo_call.get_family_usage`

getFamilyUsage — Kiểm tra dung lượng sử dụng gói ZCloud Gia đình (Family Usage - command 12758) (chưa tự động: goi 0 request (nhieu buoc hoac khong goi))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_family_usage
```

---

<a id="get_family_viewer_key"></a>
#### getFamilyViewerKey — `zalo_call.get_family_viewer_key`

getFamilyViewerKey — Lấy cặp khóa phiên (viewer_key và khóa giải mã AES-256 enk) cho gói gia đình ZFamily (command 12759). Tự động cache trong bộ nhớ ctx.zfamilyViewerKeyCache (TTL 15 phút) để tối ưu hiệu năng khi gọi liên tiếp. (chưa tự độ

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_family_viewer_key
```

---

<a id="get_usage_my_cloud"></a>
#### getUsageMyCloud — `zalo_call.get_usage_my_cloud`

getUsageMyCloud — Kiểm tra hạn mức và dung lượng sử dụng Cloud của tôi (MyCloud - command 12748) (chưa tự động: goi 0 request (nhieu buoc hoac khong goi))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_usage_my_cloud
```

---

<a id="get_usage_z_cloud"></a>
#### getUsageZCloud — `zalo_call.get_usage_z_cloud`

getUsageZCloud — Kiểm tra dung lượng sử dụng ZCloud V2 (bao gồm MyCloud và Sao lưu tin nhắn - command 12749) (chưa tự động: goi 0 request (nhieu buoc hoac khong goi))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_usage_z_cloud
```

---

<a id="migrate_cloud_recent"></a>
#### migrateCloudRecent — `zalo_call.migrate_cloud_recent`

migrateCloudRecent — Thực hiện di trú dữ liệu tệp tin gần đây lên ZCloud (command 12753) (chưa tự động: goi 0 request (nhieu buoc hoac khong goi))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.migrate_cloud_recent
```

---

<a id="reset_cloud_queue"></a>
#### resetCloudQueue — `zalo_call.reset_cloud_queue`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

resetCloudQueue — Đặt lại hàng đợi đồng bộ Media trên ZCloud (command 12744) (chưa tự động: goi 0 request (nhieu buoc hoac khong goi)) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.reset_cloud_queue
data:
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="submit_cloud_media_ext_info"></a>
#### submitCloudMediaExtInfo — `zalo_call.submit_cloud_media_ext_info`

submitCloudMediaExtInfo — Gửi thông tin mở rộng (siêu dữ liệu / khóa giải mã) của các tệp Media lên hàng đợi ZCloud (command 12745) (chưa tự động: goi 0 request (nhieu buoc hoac khong goi))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.submit_cloud_media_ext_info
```

---

<a id="submit_cloud_verify_action"></a>
#### submitCloudVerifyAction — `zalo_call.submit_cloud_verify_action`

submitCloudVerifyAction — Gửi hành động xác thực bảo mật ZCloud (Onboarding ACK V2 - command 12750) (chưa tự động: goi 0 request (nhieu buoc hoac khong goi))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.submit_cloud_verify_action
```

---

<a id="verify_cloud_media"></a>
#### verifyCloudMedia — `zalo_call.verify_cloud_media`

verifyCloudMedia — Kiểm tra và lấy danh sách mục Media lưu trữ trên ZCloud (command 12740 / 12761) (chưa tự động: goi 0 request (nhieu buoc hoac khong goi))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.verify_cloud_media
```

---

## Cuộc gọi theo thư viện zca-js (nâng cao)

<a id="add_user_group_call"></a>
#### addUserGroupCall — `zalo_call.add_user_group_call`

addUserGroupCall — Mời thêm thành viên mới vào cuộc gọi nhóm đang diễn ra (cmd 12435 - /api/voicecall/group/adduser). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.add_user_group_call
```

---

<a id="answer_ack_voice_call"></a>
#### answerAckVoiceCall — `zalo_call.answer_ack_voice_call`

answerAckVoiceCall — Gửi xác nhận hoàn tất bắt tay nhận cuộc gọi 1-1 (cmd 11304 - /api/voicecall/answerack, signal 408). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.answer_ack_voice_call
```

---

<a id="answer_group_call"></a>
#### answerGroupCall — `zalo_call.answer_group_call`

answerGroupCall — Chấp nhận tham gia cuộc gọi nhóm khi nhận được lời mời (cmd 12436 - /api/voicecall/group/answer). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.answer_group_call
```

---

<a id="answer_voice_call"></a>
#### answerVoiceCall — `zalo_call.answer_voice_call`

answerVoiceCall — Chấp nhận (Bắt máy) cuộc gọi Thoại/Video 1-1 đến (cmd 11303 - /api/voicecall/answer, signal 402). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.answer_voice_call
```

---

<a id="broadcast_group_call_state"></a>
#### broadcastGroupCallState — `zalo_call.broadcast_group_call_state`

broadcastGroupCallState — Phát quảng bá trạng thái thiết bị (Mic, Camera, Screen Share) tới các thành viên trong cuộc gọi nhóm (cmd 12098 - /api/voicecall/group/broadcast). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.broadcast_group_call_state
```

---

<a id="cancel_group_call"></a>
#### cancelGroupCall — `zalo_call.cancel_group_call`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

cancelGroupCall — Hủy lời mời cuộc gọi nhóm (cmd 12437 - /api/voicecall/group/cancel). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet)) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.cancel_group_call
data:
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="cancel_voice_call"></a>
#### cancelVoiceCall — `zalo_call.cancel_voice_call`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

cancelVoiceCall — Hủy cuộc gọi 1-1 đang đổ chuông trước khi người nhận bắt máy (cmd 11305 - /api/voicecall/cancel, signal 405). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet)) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.cancel_voice_call
data:
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="create_controller"></a>
#### createController — `zalo_call.create_controller`

createController — Khởi tạo bộ điều phối cuộc gọi ZaloCallController quản lý vòng đời gọi đi, nhận cuộc gọi đến và kênh IPC cục bộ. (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.create_controller
```

---

<a id="create_rtc_session"></a>
#### createRtcSession — `zalo_call.create_rtc_session`

createRtcSession — Khởi tạo phiên gọi thoại / video 2 chiều thuần TypeScript (ZaloRtcSession — UDP ZRTPPacket + SRTP + H.264 Annex-B + Mobile Direct UDP Handoff). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.create_rtc_session
```

---

<a id="end_group_call"></a>
#### endGroupCall — `zalo_call.end_group_call`

endGroupCall — Rời khỏi cuộc gọi nhóm hoặc từ chối lời mời gọi nhóm (cmd 12438 - /api/voicecall/group/endcall). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.end_group_call
```

---

<a id="end_voice_call"></a>
#### endVoiceCall — `zalo_call.end_voice_call`

endVoiceCall — Kết thúc cuộc gọi 1-1 đang diễn ra hoặc từ chối cuộc gọi đến (cmd 11306 - /api/voicecall/endcall, signal 404). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.end_voice_call
```

---

<a id="finish_group_call"></a>
#### finishGroupCall — `zalo_call.finish_group_call`

finishGroupCall — Kết thúc hoàn toàn phòng gọi nhóm cho tất cả thành viên (cmd 12446 - /api/voicecall/group/finish). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.finish_group_call
```

---

<a id="get_group_call_state"></a>
#### getGroupCallState — `zalo_call.get_group_call_state`

getGroupCallState — Truy vấn trạng thái hiện tại và danh sách thành viên trong phòng gọi nhóm (cmd 12445 - /api/voicecall/group/state). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_group_call_state
```

---

<a id="hold_voice_call"></a>
#### holdVoiceCall — `zalo_call.hold_voice_call`

holdVoiceCall — Tạm giữ (Hold) cuộc gọi 1-1 đang diễn ra hoặc phản hồi yêu cầu tạm giữ (cmd 11307 holdreq / cmd 11308 holdresp, signal 411/412). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.hold_voice_call
```

---

<a id="join_group_call"></a>
#### joinGroupCall — `zalo_call.join_group_call`

joinGroupCall — Chủ động tham gia vào một cuộc gọi nhóm đang diễn ra từ banner nhóm (cmd 12043 - /api/voicecall/group/join). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.join_group_call
```

---

<a id="log_end_voice_call"></a>
#### logEndVoiceCall — `zalo_call.log_end_voice_call`

logEndVoiceCall — Gửi thống kê chất lượng cuộc gọi (QoS/Billing stats) sau khi kết thúc cuộc gọi 1-1 (cmd 11311 - /api/voicecall/logendcall, signal 406). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.log_end_voice_call
```

---

<a id="notify_group_call"></a>
#### notifyGroupCall — `zalo_call.notify_group_call`

notifyGroupCall — Gửi thông báo sự kiện cuộc gọi nhóm vào luồng chat nhóm (cmd 12447 - /api/voicecall/group/notify). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.notify_group_call
```

---

<a id="ping_group_call"></a>
#### pingGroupCall — `zalo_call.ping_group_call`

pingGroupCall — Gửi nhịp tim (Heartbeat Ping) duy trì kết nối của thành viên trong phòng gọi nhóm (cmd 12097 - /api/voicecall/group/ping). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.ping_group_call
```

---

<a id="request_audio_to_video_call"></a>
#### requestAudioToVideoCall — `zalo_call.request_audio_to_video_call`

requestAudioToVideoCall — Yêu cầu nâng cấp từ cuộc gọi Thoại sang cuộc gọi Video hoặc phản hồi yêu cầu (cmd 12056 - /api/voicecall/requestaudio2video). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.request_audio_to_video_call
```

---

<a id="request_group_call"></a>
#### requestGroupCall — `zalo_call.request_group_call`

requestGroupCall — Bước 1 gọi nhóm (cmd 12433 - /api/voicecall/group/requestcall): Xin cấp phát phòng gọi nhóm (Group Call Room & RTP/ZRTC servers). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.request_group_call
```

---

<a id="request_share_screen_call"></a>
#### requestShareScreenCall — `zalo_call.request_share_screen_call`

requestShareScreenCall — Yêu cầu bắt đầu hoặc kết thúc chia sẻ màn hình (Screen Share) trong cuộc gọi 1-1 (cmd 12064 - /api/voicecall/requestsharescreen). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.request_share_screen_call
```

---

<a id="request_voice_call"></a>
#### requestVoiceCall — `zalo_call.request_voice_call`

requestVoiceCall — Bước 1 gọi 1-1 (cmd 11300 - /api/voicecall/requestcall, signal 401): Xin cấp phát phòng gọi 1-1 (callId, sessId, rtpServer, rtcpServer, zrtpKey, codec). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.request_voice_call
```

---

<a id="ring_ring_group_call"></a>
#### ringRingGroupCall — `zalo_call.ring_ring_group_call`

ringRingGroupCall — Báo hiệu thiết bị đang đổ chuông cho lời mời gọi nhóm (cmd 12439 - /api/voicecall/group/ringring). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.ring_ring_group_call
```

---

<a id="ring_ring_voice_call"></a>
#### ringRingVoiceCall — `zalo_call.ring_ring_voice_call`

ringRingVoiceCall — Báo hiệu thiết bị đang đổ chuông cho cuộc gọi 1-1 đến (cmd 11302 - /api/voicecall/ringring, signal 407). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.ring_ring_voice_call
```

---

<a id="send_request_group_call"></a>
#### sendRequestGroupCall — `zalo_call.send_request_group_call`

sendRequestGroupCall — Bước 2 gọi nhóm (cmd 12434 - /api/voicecall/group/request): Phát tín hiệu mời gọi nhóm tới danh sách thành viên. (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_request_group_call
```

---

<a id="send_request_voice_call"></a>
#### sendRequestVoiceCall — `zalo_call.send_request_voice_call`

sendRequestVoiceCall — Bước 2 gọi 1-1 (cmd 11301 - /api/voicecall/request, signal 416): Gửi gói mời gọi (Invite) kèm extendData ZRTC để kích hoạt đổ chuông trên thiết bị người nhận. (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_request_voice_call
```

---

<a id="send_voice_call"></a>
#### sendVoiceCall — `zalo_call.send_voice_call`

sendVoiceCall — Khởi tạo cuộc gọi Thoại hoặc Video 1-1 trọn gói (tự động thực hiện 2 bước 11300 + 11301 làm đổ chuông máy người nhận). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.send_voice_call
```

---

<a id="share_screen_group_call"></a>
#### shareScreenGroupCall — `zalo_call.share_screen_group_call`

shareScreenGroupCall — Bắt đầu hoặc dừng chia sẻ màn hình trong cuộc gọi nhóm (cmd 12044 - /api/voicecall/group/sharescreen). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.share_screen_group_call
```

---

<a id="unhold_voice_call"></a>
#### unholdVoiceCall — `zalo_call.unhold_voice_call`

unholdVoiceCall — Khôi phục (Unhold) cuộc gọi 1-1 đang tạm giữ hoặc phản hồi yêu cầu khôi phục (cmd 11309 unholdreq / cmd 11310 unholdresp, signal 413/414). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.unhold_voice_call
```

---

<a id="update_call_media_state"></a>
#### updateCallMediaState — `zalo_call.update_call_media_state`

updateCallMediaState — Đồng bộ trạng thái bật/tắt Mic và Camera trong cuộc gọi 1-1 (cmd 12006 - /api/voicecall/conf). (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_call_media_state
```

---

## Phương tiện

<a id="get_conversation_media"></a>
#### getConversationMedia — `zalo_call.get_conversation_media`

getConversationMedia — Lấy danh sách Kho Lưu Trữ (Ảnh/Video "media", File "file", hoặc Link "link") trong hội thoại nhóm (command 11841)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_conversation_media
data:
  groupId: "..."      # tuỳ chọn - groupId
  threadId: "..."     # tuỳ chọn - threadId
  mediaType: "..."    # tuỳ chọn - mediaType
  limit: "..."        # tuỳ chọn - limit
  lastId: "..."       # tuỳ chọn - lastId
  lastFetchId: "..."  # tuỳ chọn - lastFetchId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | không | groupId (string) |
| `threadId` | threadId | không | threadId (string) |
| `mediaType` | mediaType | không | mediaType (MediaStoreType) |
| `limit` | limit | không | limit (number) |
| `lastId` | lastId | không | lastId (number \| string) |
| `lastFetchId` | lastFetchId | không | lastFetchId (number) |

---

<a id="get_media_store_preview"></a>
#### getMediaStorePreview — `zalo_call.get_media_store_preview`

getMediaStorePreview — Lấy danh sách xem trước nhanh Kho Lưu Trữ (Ảnh/Video, File, Link) của nhóm (command 11843)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_media_store_preview
data:
  groupId: "..."  # bắt buộc - groupId
  limit: "..."    # tuỳ chọn - limit
  params: {}      # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | ID của nhóm (string) |
| `limit` | limit | không | Số lượng mục tối đa (mặc định: 50) (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_personal_media"></a>
#### getPersonalMedia — `zalo_call.get_personal_media`

getPersonalMedia — Lấy danh sách Kho Lưu Trữ Ảnh/Video ("media"), File ("file"), hoặc Link ("link") trong Cloud của tôi (Send2Me) (command 12220)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_personal_media
data:
  mediaType: "..."    # tuỳ chọn - mediaType
  limit: "..."        # tuỳ chọn - limit
  lastId: "..."       # tuỳ chọn - lastId
  lastFetchId: "..."  # tuỳ chọn - lastFetchId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `mediaType` | mediaType | không | mediaType (MediaStoreType) |
| `limit` | limit | không | limit (number) |
| `lastId` | lastId | không | lastId (number \| string) |
| `lastFetchId` | lastFetchId | không | lastFetchId (number) |

---

<a id="get_personal_media_preview"></a>
#### getPersonalMediaPreview — `zalo_call.get_personal_media_preview`

getPersonalMediaPreview — Lấy danh sách xem trước nhanh Kho Lưu Trữ trong Cloud của tôi (Send2Me) (command 12221)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_personal_media_preview
data:
  limit: "..."  # tuỳ chọn - limit
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `limit` | limit | không | Số lượng mục tối đa (mặc định: `50`) (number) |

---

<a id="remove_conversation_media"></a>
#### removeConversationMedia — `zalo_call.remove_conversation_media`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

removeConversationMedia — Xóa mục Ảnh/Video, File hoặc Link khỏi Kho Lưu Trữ của nhóm (command 11842) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_conversation_media
data:
  groupId: "..."    # bắt buộc - groupId
  mediaType: "..."  # bắt buộc - mediaType
  mediaId: "..."    # bắt buộc - mediaId
  params: {}        # bắt buộc - params
  confirm: false    # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | groupId (string) |
| `mediaType` | mediaType | có | mediaType (MediaStoreType) |
| `mediaId` | mediaId | có | mediaId (string \| number \| (string \| number)[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="remove_personal_media"></a>
#### removePersonalMedia — `zalo_call.remove_personal_media`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

removePersonalMedia — Xóa mục lưu trữ trong Kho Lưu Trữ Cloud của tôi (Send2Me) (command 12222) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_personal_media
data:
  mediaType: "..."  # bắt buộc - mediaType
  mediaId: "..."    # bắt buộc - mediaId
  confirm: false    # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `mediaType` | mediaType | có | mediaType (MediaStoreType) |
| `mediaId` | mediaId | có | mediaId (number \| string \| Array<number \| string>) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="upload_attachment"></a>
#### uploadAttachment — `zalo_call.upload_attachment`

uploadAttachment — Tải tệp đính kèm (Ảnh, Video, File) lên máy chủ Zalo để lấy thông tin fileUrl / fileId trước khi gửi. (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet))

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.upload_attachment
```

---

## Sticker (nâng cao)

<a id="get_a_i_sticker_list"></a>
#### getAIStickerList — `zalo_call.get_a_i_sticker_list`

getAIStickerList — Lấy danh sách Sticker AI của người dùng (command 12190)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_a_i_sticker_list
```

---

<a id="get_default_guggy_gifs"></a>
#### getDefaultGuggyGifs — `zalo_call.get_default_guggy_gifs`

getDefaultGuggyGifs — Lấy danh sách ảnh động Guggy GIF mặc định (command 11749)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_default_guggy_gifs
data:
  limit: "..."  # tuỳ chọn - limit
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `limit` | limit | không | Số lượng kết quả tối đa (mặc định `10`) (number) |

---

<a id="get_gif_categories"></a>
#### getGifCategories — `zalo_call.get_gif_categories`

getGifCategories — Lấy danh sách danh mục ảnh động Giphy GIF (command 11294)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_gif_categories
data:
  offset: "..."  # tuỳ chọn - offset
  limit: "..."   # tuỳ chọn - limit
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `offset` | offset | không | Vị trí bắt đầu (mặc định `0`) (number) |
| `limit` | limit | không | Số lượng kết quả tối đa (mặc định `10`) (number) |

---

<a id="get_gif_dictionaries"></a>
#### getGifDictionaries — `zalo_call.get_gif_dictionaries`

getGifDictionaries — Lấy danh sách từ điển ảnh động Giphy GIF (command 11298)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_gif_dictionaries
data:
  offset: "..."  # tuỳ chọn - offset
  limit: "..."   # tuỳ chọn - limit
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `offset` | offset | không | Vị trí bắt đầu (mặc định `0`) (number) |
| `limit` | limit | không | Số lượng kết quả tối đa (mặc định `10`) (number) |

---

<a id="get_gifs_by_category"></a>
#### getGifsByCategory — `zalo_call.get_gifs_by_category`

getGifsByCategory — Lấy danh sách ảnh động Giphy GIF theo ID danh mục (command 11295)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_gifs_by_category
data:
  cateId: "..."  # bắt buộc - cateId
  offset: "..."  # tuỳ chọn - offset
  limit: "..."   # tuỳ chọn - limit
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `cateId` | cateId | có | ID danh mục GIF (number) |
| `offset` | offset | không | Vị trí bắt đầu (mặc định `0`) (number) |
| `limit` | limit | không | Số lượng kết quả tối đa (mặc định `10`) (number) |

---

<a id="get_gifs_by_dictionary"></a>
#### getGifsByDictionary — `zalo_call.get_gifs_by_dictionary`

getGifsByDictionary — Lấy danh sách ảnh động Giphy GIF theo ID từ điển (command 11299)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_gifs_by_dictionary
data:
  dicId: "..."   # bắt buộc - dicId
  offset: "..."  # tuỳ chọn - offset
  limit: "..."   # tuỳ chọn - limit
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `dicId` | dicId | có | ID từ điển GIF (number) |
| `offset` | offset | không | Vị trí bắt đầu (mặc định `0`) (number) |
| `limit` | limit | không | Số lượng kết quả tối đa (mặc định `10`) (number) |

---

<a id="get_message_effect_by_id"></a>
#### getMessageEffectById — `zalo_call.get_message_effect_by_id`

getMessageEffectById — Lấy chi tiết một hiệu ứng tin nhắn theo ID và kích thước (command 11743)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_message_effect_by_id
data:
  id: "..."    # bắt buộc - id
  size: "..."  # tuỳ chọn - size
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `id` | id | có | ID hiệu ứng (number \| string) |
| `size` | size | không | Kích thước tài nguyên hiệu ứng (mặc định `130`) (number) |

---

<a id="get_message_effects"></a>
#### getMessageEffects — `zalo_call.get_message_effects`

getMessageEffects — Lấy thông tin hiệu ứng tin nhắn theo danh sách ID (command 11742)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_message_effects
data:
  effectIds: "..."  # tuỳ chọn - effectIds
  params: {}        # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `effectIds` | effectIds | không | ID hoặc danh sách ID hiệu ứng (number \| number[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_personalized_sticker_list"></a>
#### getPersonalizedStickerList — `zalo_call.get_personalized_sticker_list`

getPersonalizedStickerList — Lấy danh sách Sticker cá nhân hóa của tài khoản (command 11745)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_personalized_sticker_list
```

---

<a id="get_recommended_stickers"></a>
#### getRecommendedStickers — `zalo_call.get_recommended_stickers`

getRecommendedStickers — Lấy danh sách các bộ Sticker được Zalo đề xuất (command 11748)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_recommended_stickers
```

---

<a id="get_sticker_categories_v2"></a>
#### getStickerCategoriesV2 — `zalo_call.get_sticker_categories_v2`

getStickerCategoriesV2 — Lấy danh sách danh mục bộ nhãn dán (Sticker Categories V2 - command 12020) (chưa tự động: khong doc duoc doi tuong params)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_sticker_categories_v2
```

---

<a id="get_sticker_category_detail"></a>
#### getStickerCategoryDetail — `zalo_call.get_sticker_category_detail`

getStickerCategoryDetail — Lấy danh sách toàn bộ nhãn dán nằm trong một bộ nhãn dán (Category/Pack ID).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_sticker_category_detail
data:
  cateId: "..."  # bắt buộc - cateId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `cateId` | cateId | có | Sticker category ID (number) |

---

<a id="get_sticker_hello"></a>
#### getStickerHello — `zalo_call.get_sticker_hello`

getStickerHello — Lấy danh sách Sticker chào hỏi gợi ý khi bắt đầu trò chuyện mới (command 11751)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_sticker_hello
```

---

<a id="get_sticker_suggest_keywords"></a>
#### getStickerSuggestKeywords — `zalo_call.get_sticker_suggest_keywords`

getStickerSuggestKeywords — Lấy bộ từ khóa gợi ý Sticker tự động khi gõ tin nhắn (command 11740)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_sticker_suggest_keywords
```

---

<a id="get_sticker_suggestion"></a>
#### getStickerSuggestion — `zalo_call.get_sticker_suggestion`

getStickerSuggestion — Gợi ý Sticker/GIF theo từ khóa đang nhập (command 11741)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_sticker_suggestion
data:
  options: "{\"voice\": \"nova\"}"  # bắt buộc - options
  params: {}                        # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `options` | options | có | Từ khóa và tùy chọn kèm theo (`gif`, `guggy`) (GetStickerSuggestionOptions \| string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_tenor_sticker_mapping"></a>
#### getTenorStickerMapping — `zalo_call.get_tenor_sticker_mapping`

getTenorStickerMapping — Lấy bảng ánh xạ Tenor sang Sticker Zalo (command 12015)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_tenor_sticker_mapping
```

---

<a id="get_trending_gifs"></a>
#### getTrendingGifs — `zalo_call.get_trending_gifs`

getTrendingGifs — Lấy danh sách ảnh động Giphy GIF thịnh hành (command 11296)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_trending_gifs
data:
  offset: "..."  # tuỳ chọn - offset
  limit: "..."   # tuỳ chọn - limit
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `offset` | offset | không | Vị trí bắt đầu (mặc định `0`) (number) |
| `limit` | limit | không | Số lượng kết quả tối đa (mặc định `10`) (number) |

---

<a id="search_gifs"></a>
#### searchGifs — `zalo_call.search_gifs`

searchGifs — Tìm kiếm ảnh động Giphy GIF theo từ khóa (command 11297)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.search_gifs
data:
  keyword: "/qm1"  # bắt buộc - keyword
  offset: "..."    # tuỳ chọn - offset
  limit: "..."     # tuỳ chọn - limit
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `keyword` | keyword | có | Từ khóa tìm kiếm (string) |
| `offset` | offset | không | Vị trí bắt đầu (mặc định `0`) (number) |
| `limit` | limit | không | Số lượng kết quả tối đa (mặc định `10`) (number) |

---

<a id="search_guggy_gifs"></a>
#### searchGuggyGifs — `zalo_call.search_guggy_gifs`

searchGuggyGifs — Tìm kiếm ảnh động Guggy GIF theo từ khóa (command 11750)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.search_guggy_gifs
data:
  keyword: "/qm1"  # bắt buộc - keyword
  limit: "..."     # tuỳ chọn - limit
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `keyword` | keyword | có | Từ khóa tìm kiếm (string) |
| `limit` | limit | không | Số lượng kết quả tối đa (mặc định `10`) (number) |

---

<a id="search_sticker"></a>
#### searchSticker — `zalo_call.search_sticker`

searchSticker — Tìm kiếm nhãn dán nâng cao theo từ khóa.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.search_sticker
data:
  keyword: "/qm1"  # bắt buộc - keyword
  limit: "..."     # tuỳ chọn - limit
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `keyword` | keyword | có | Keyword to search stickers (string) |
| `limit` | limit | không | Limit of stickers to return (default: 50) (number) |

---

<a id="update_personalized_sticker_list"></a>
#### updatePersonalizedStickerList — `zalo_call.update_personalized_sticker_list`

updatePersonalizedStickerList — Cập nhật danh sách các bộ Sticker cá nhân hóa của người dùng (command 11746)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_personalized_sticker_list
data:
  stickerCateIds: "..."  # bắt buộc - stickerCateIds
  version: "..."         # tuỳ chọn - version
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `stickerCateIds` | stickerCateIds | có | Danh sách ID danh mục Sticker (number[]) |
| `version` | version | không | Phiên bản hiện tại của danh sách (number) |

---

## Ghi chú, bình chọn, việc cần làm

<a id="ack_ding_todo"></a>
#### ackDingTodo — `zalo_call.ack_ding_todo`

ackDingTodo — Xác nhận đã nhận nhắc nhở (Ding ACK) trong Zalo To-Do (command 12427)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.ack_ding_todo
data:
  taskIds: "..."  # bắt buộc - taskIds
  params: {}      # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `taskIds` | taskIds | có | Danh sách ID công việc xác nhận (string \| string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="add_poll_options"></a>
#### addPollOptions — `zalo_call.add_poll_options`

addPollOptions — Thêm phương án lựa chọn mới vào một cuộc Bình chọn (Poll) đang mở trong nhóm.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.add_poll_options
data:
  pollId: "..."                     # bắt buộc - pollId
  options: "{\"voice\": \"nova\"}"  # bắt buộc - options
  votedOptionIds: "..."             # bắt buộc - votedOptionIds
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `pollId` | pollId | có | pollId (number) |
| `options` | options | có | options (AddPollOptionsOption[]) |
| `votedOptionIds` | votedOptionIds | có | votedOptionIds (number[]) |

---

<a id="create_note"></a>
#### createNote — `zalo_call.create_note`

createNote — Tạo một Ghi chú (Note) mới trên Bảng tin nhóm và tùy chọn ghim lên đầu.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.create_note
data:
  options: "{\"voice\": \"nova\"}"  # bắt buộc - options
  groupId: "..."                    # bắt buộc - groupId
  params: {}                        # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `options` | options | có | note options (CreateNoteOptions) |
| `groupId` | groupId | có | group id (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="create_todo"></a>
#### createTodo — `zalo_call.create_todo`

createTodo — Tạo công việc mới trong Zalo To-Do (command 12413)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.create_todo
data:
  title: "Họp nhóm"                 # tuỳ chọn - title
  content: "Họp nhóm lúc 10h sáng"  # tuỳ chọn - content
  assignees: "..."                  # tuỳ chọn - assignees
  watchers: "..."                   # tuỳ chọn - watchers
  dueDate: "..."                    # tuỳ chọn - dueDate
  dateDefaultType: "..."            # tuỳ chọn - dateDefaultType
  status: 1                         # tuỳ chọn - status
  schedule: "..."                   # tuỳ chọn - schedule
  src: "..."                        # tuỳ chọn - src
  key: "..."                        # bắt buộc - key
  params: {}                        # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `title` | title | không | title (string) |
| `content` | content | không | content (string) |
| `assignees` | assignees | không | assignees (string[]) |
| `watchers` | watchers | không | watchers (string[]) |
| `dueDate` | dueDate | không | dueDate (number) |
| `dateDefaultType` | dateDefaultType | không | dateDefaultType (number) |
| `status` | status | không | status (number) |
| `schedule` | schedule | không | schedule (unknown) |
| `src` | src | không | src (number) |
| `key` | key | có | key (string]: unknown) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

**Các lựa chọn:**

- **status** (`status`)
  - `1`: mã trạng thái 1 của Zalo (app chưa chú giải nghĩa)
  - `0`: mã trạng thái 0 của Zalo (app chưa chú giải nghĩa)

---

<a id="delete_todo"></a>
#### deleteTodo — `zalo_call.delete_todo`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

deleteTodo — Xóa công việc trong Zalo To-Do (command 12415) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.delete_todo
data:
  todoId: "..."   # bắt buộc - todoId
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `todoId` | todoId | có | ID công việc cần xóa (string) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="ding_todo"></a>
#### dingTodo — `zalo_call.ding_todo`

dingTodo — Gửi nhắc nhở (Ding) cho các công việc trong Zalo To-Do (command 12426)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.ding_todo
data:
  taskIds: "..."  # bắt buộc - taskIds
  params: {}      # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `taskIds` | taskIds | có | Danh sách ID công việc cần nhắc nhở (string \| string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="edit_note"></a>
#### editNote — `zalo_call.edit_note`

editNote — Chỉnh sửa nội dung ghi chú đã tạo trên Bảng tin nhóm.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.edit_note
data:
  options: "{\"voice\": \"nova\"}"  # bắt buộc - options
  groupId: "..."                    # bắt buộc - groupId
  params: {}                        # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `options` | options | có | Options for editing the note (EditNoteOptions) |
| `groupId` | groupId | có | Group ID to create note from (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_list_pin_topics"></a>
#### getListPinTopics — `zalo_call.get_list_pin_topics`

getListPinTopics — Lấy danh sách chủ đề / tin nhắn đã ghim trong bảng tin nhóm (command 12001)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_list_pin_topics
data:
  groupId: "..."       # bắt buộc - groupId
  boardVersion: "..."  # tuỳ chọn - boardVersion
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | ID nhóm (string) |
| `boardVersion` | boardVersion | không | Phiên bản bảng ghim hiện tại (mặc định `0`) (number) |

---

<a id="get_todo_detail"></a>
#### getTodoDetail — `zalo_call.get_todo_detail`

getTodoDetail — Lấy chi tiết công việc trong Zalo To-Do (command 12417)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_todo_detail
data:
  todoId: "..."  # bắt buộc - todoId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `todoId` | todoId | có | ID công việc (string) |

---

<a id="get_todo_list"></a>
#### getTodoList — `zalo_call.get_todo_list`

getTodoList — Lấy danh sách công việc trong Zalo To-Do (command 12416)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_todo_list
data:
  scrollId: "..."  # tuỳ chọn - scrollId
  queries: "..."   # tuỳ chọn - queries
  offset: "..."    # tuỳ chọn - offset
  limit: "..."     # tuỳ chọn - limit
  type: 0          # tuỳ chọn - type
  params: {}       # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `scrollId` | scrollId | không | scrollId (string) |
| `queries` | queries | không | queries (Record<string, unknown> \| string) |
| `offset` | offset | không | offset (number) |
| `limit` | limit | không | limit (number) |
| `type` | type | không | type (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

**Các lựa chọn:**

- **type** (`type`)
  - `0`: mã 0 của Zalo (app chưa chú giải nghĩa; giữ mặc định nếu không chắc)
  - `1`: mã 1 của Zalo (app chưa chú giải nghĩa; giữ mặc định nếu không chắc)

---

<a id="multi_unpin_board_topics"></a>
#### multiUnpinBoardTopics — `zalo_call.multi_unpin_board_topics`

multiUnpinBoardTopics — Bỏ ghim đồng thời nhiều chủ đề khỏi bảng tin nhóm (command 12010)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.multi_unpin_board_topics
data:
  groupId: "..."       # bắt buộc - groupId
  topics: "..."        # bắt buộc - topics
  boardVersion: "..."  # tuỳ chọn - boardVersion
  params: {}           # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | ID nhóm (string) |
| `topics` | topics | có | Danh sách chủ đề cần bỏ ghim (unknown[]) |
| `boardVersion` | boardVersion | không | Phiên bản bảng ghim hiện tại (mặc định `0`) (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="pin_board_topic"></a>
#### pinBoardTopic — `zalo_call.pin_board_topic`

pinBoardTopic — Ghim một chủ đề / bài đăng lên bảng tin nhóm (command 12004)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.pin_board_topic
data:
  groupId: "..."  # bắt buộc - groupId
  topicId: "..."  # bắt buộc - topicId
  type: 0         # bắt buộc - type
  params: {}      # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | ID nhóm (string) |
| `topicId` | topicId | có | ID chủ đề cần ghim (string) |
| `type` | type | có | Loại chủ đề (ví dụ: ghi chú, bình chọn, nhắc hẹn) (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

**Các lựa chọn:**

- **type** (`type`)
  - `0`: loại chủ đề mã 0 của Zalo (ghi chú, bình chọn, nhắc hẹn; app chưa chú giải mã nào là loại nào)
  - `1`: loại chủ đề mã 1 của Zalo (app chưa chú giải)

---

<a id="pin_friend_message"></a>
#### pinFriendMessage — `zalo_call.pin_friend_message`

pinFriendMessage — Ghim tin nhắn / chủ đề trong hội thoại cá nhân 1-1 (command 12067)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.pin_friend_message
data:
  conversationId: "..."  # bắt buộc - conversationId
  topic: "..."           # bắt buộc - topic
  version: "..."         # tuỳ chọn - version
  params: {}             # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `conversationId` | conversationId | có | ID hội thoại 1-1 (string) |
| `topic` | topic | có | Thông tin tin nhắn / chủ đề cần ghim (unknown) |
| `version` | version | không | Phiên bản bảng ghim hiện tại (mặc định `0`) (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="reorder_friend_board"></a>
#### reorderFriendBoard — `zalo_call.reorder_friend_board`

reorderFriendBoard — Sắp xếp lại thứ tự các tin nhắn đã ghim trong hội thoại 1-1 (command 12068)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.reorder_friend_board
data:
  conversationId: "..."  # bắt buộc - conversationId
  topics: "..."          # bắt buộc - topics
  version: "..."         # tuỳ chọn - version
  params: {}             # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `conversationId` | conversationId | có | ID hội thoại 1-1 (string) |
| `topics` | topics | có | Danh sách tin nhắn đã ghim theo thứ tự mới (unknown[]) |
| `version` | version | không | Phiên bản bảng ghim hiện tại (mặc định `0`) (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="reorder_pin_topics"></a>
#### reorderPinTopics — `zalo_call.reorder_pin_topics`

reorderPinTopics — Sắp xếp lại thứ tự các chủ đề đã ghim trên bảng tin nhóm (command 12002)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.reorder_pin_topics
data:
  groupId: "..."       # bắt buộc - groupId
  topics: "..."        # bắt buộc - topics
  boardVersion: "..."  # tuỳ chọn - boardVersion
  params: {}           # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | ID nhóm (string) |
| `topics` | topics | có | Danh sách chủ đề đã ghim theo thứ tự mới (unknown[]) |
| `boardVersion` | boardVersion | không | Phiên bản bảng ghim hiện tại (mặc định `0`) (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="share_poll"></a>
#### sharePoll — `zalo_call.share_poll`

sharePoll — Chia sẻ lại cuộc Bình chọn vào luồng tin nhắn nhóm.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.share_poll
data:
  pollId: "..."  # bắt buộc - pollId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `pollId` | pollId | có | poll id to share (number) |

---

<a id="unpin_board_topic"></a>
#### unpinBoardTopic — `zalo_call.unpin_board_topic`

unpinBoardTopic — Bỏ ghim một chủ đề khỏi bảng tin nhóm (command 12005)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.unpin_board_topic
data:
  groupId: "..."       # bắt buộc - groupId
  topic: "..."         # bắt buộc - topic
  boardVersion: "..."  # tuỳ chọn - boardVersion
  params: {}           # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `groupId` | groupId | có | ID nhóm (string) |
| `topic` | topic | có | Thông tin chủ đề cần bỏ ghim (hoặc `{ id, type }`) (unknown) |
| `boardVersion` | boardVersion | không | Phiên bản bảng ghim hiện tại (mặc định `0`) (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="unpin_friend_messages"></a>
#### unpinFriendMessages — `zalo_call.unpin_friend_messages`

unpinFriendMessages — Bỏ ghim một hoặc nhiều tin nhắn trong hội thoại 1-1 (command 12069)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.unpin_friend_messages
data:
  conversationId: "..."  # bắt buộc - conversationId
  topics: "..."          # bắt buộc - topics
  version: "..."         # tuỳ chọn - version
  params: {}             # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `conversationId` | conversationId | có | ID hội thoại 1-1 (string) |
| `topics` | topics | có | Danh sách tin nhắn / chủ đề cần bỏ ghim (unknown[]) |
| `version` | version | không | Phiên bản bảng ghim hiện tại (mặc định `0`) (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="update_todo"></a>
#### updateTodo — `zalo_call.update_todo`

updateTodo — Cập nhật nội dung công việc trong Zalo To-Do (command 12414)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_todo
data:
  id: "..."                         # bắt buộc - id
  title: "Họp nhóm"                 # tuỳ chọn - title
  content: "Họp nhóm lúc 10h sáng"  # tuỳ chọn - content
  assignees: "..."                  # tuỳ chọn - assignees
  watchers: "..."                   # tuỳ chọn - watchers
  dueDate: "..."                    # tuỳ chọn - dueDate
  dateDefaultType: "..."            # tuỳ chọn - dateDefaultType
  status: 1                         # tuỳ chọn - status
  schedule: "..."                   # tuỳ chọn - schedule
  key: "..."                        # bắt buộc - key
  params: {}                        # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `id` | id | có | id (string) |
| `title` | title | không | title (string) |
| `content` | content | không | content (string) |
| `assignees` | assignees | không | assignees (string[]) |
| `watchers` | watchers | không | watchers (string[]) |
| `dueDate` | dueDate | không | dueDate (number) |
| `dateDefaultType` | dateDefaultType | không | dateDefaultType (number) |
| `status` | status | không | status (number) |
| `schedule` | schedule | không | schedule (unknown) |
| `key` | key | có | key (string]: unknown) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

**Các lựa chọn:**

- **status** (`status`)
  - `1`: mã trạng thái 1 của Zalo (app chưa chú giải nghĩa)
  - `0`: mã trạng thái 0 của Zalo (app chưa chú giải nghĩa)

---

<a id="update_todo_status"></a>
#### updateTodoStatus — `zalo_call.update_todo_status`

updateTodoStatus — Cập nhật trạng thái công việc trong Zalo To-Do (command 12418)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_todo_status
data:
  todoId: "..."  # bắt buộc - todoId
  status: 1      # bắt buộc - status
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `todoId` | todoId | có | ID công việc (string) |
| `status` | status | có | Trạng thái mới (ví dụ: đang thực hiện, hoàn thành) (number) |

**Các lựa chọn:**

- **status** (`status`)
  - `1`: mã trạng thái 1 của Zalo (app chưa chú giải nghĩa)
  - `0`: mã trạng thái 0 của Zalo (app chưa chú giải nghĩa)

---

<a id="verify_todo"></a>
#### verifyTodo — `zalo_call.verify_todo`

verifyTodo — Kiểm tra tính đồng bộ của danh sách công việc trong Zalo To-Do (command 12603)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.verify_todo
data:
  scrollId: "..."         # tuỳ chọn - scrollId
  lastUpdatedTime: "..."  # tuỳ chọn - lastUpdatedTime
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `scrollId` | scrollId | không | Mã cuộn hiện tại (string) |
| `lastUpdatedTime` | lastUpdatedTime | không | Thời điểm cập nhật cuối cùng (number) |

---

## Zalo Business (OA)

<a id="add_conversation_label"></a>
#### addConversationLabel — `zalo_call.add_conversation_label`

addConversationLabel — Tạo nhãn phân loại hội thoại mới (command 12163)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.add_conversation_label
data:
  text: "..."           # bắt buộc - text
  color: "..."          # bắt buộc - color
  emoji: "..."          # tuỳ chọn - emoji
  conversations: "..."  # tuỳ chọn - conversations
  params: {}            # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `text` | text | có | text (string) |
| `color` | color | có | color (number) |
| `emoji` | emoji | không | emoji (string) |
| `conversations` | conversations | không | conversations (string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="block_o_a"></a>
#### blockOA — `zalo_call.block_o_a`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

blockOA — Chặn nhận tin nhắn / thông báo từ một Zalo Official Account (OA) qua /api/social/oa/block (cmd 12681). (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.block_o_a
data:
  oaId: "..."     # bắt buộc - oaId
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `oaId` | oaId | có | UID hoặc OA ID của Official Account cần chặn (string) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="convert_o_a_ids"></a>
#### convertOAIds — `zalo_call.convert_o_a_ids`

convertOAIds — Chuyển đổi danh sách OA ID sang Zalo UID nội bộ (hoặc ngược lại) qua /api/social/oa/convertid (cmd 11863).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.convert_o_a_ids
data:
  oaIds: "..."  # bắt buộc - oaIds
  params: {}    # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `oaIds` | oaIds | có | Một OA ID hoặc mảng các OA ID cần chuyển đổi (string \| string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="create_auto_reply"></a>
#### createAutoReply — `zalo_call.create_auto_reply`

createAutoReply — Tạo kịch bản Trả lời tự động (Auto Reply) theo khung giờ cho Zalo Business.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.create_auto_reply
data:
  content: "Họp nhóm lúc 10h sáng"  # bắt buộc - content
  isEnable: "..."                   # bắt buộc - isEnable
  startTime: "..."                  # bắt buộc - startTime
  endTime: "..."                    # bắt buộc - endTime
  scope: "..."                      # bắt buộc - scope
  uids: "..."                       # tuỳ chọn - uids
  params: {}                        # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `content` | content | có | content (string) |
| `isEnable` | isEnable | có | isEnable (boolean) |
| `startTime` | startTime | có | startTime (number) |
| `endTime` | endTime | có | endTime (number) |
| `scope` | scope | có | scope (AutoReplyScope) |
| `uids` | uids | không | uids (string \| string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="create_bank_account"></a>
#### createBankAccount — `zalo_call.create_bank_account`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

createBankAccount — Thêm thông tin tài khoản ngân hàng mới vào danh bạ ngân hàng. (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.create_bank_account
data:
  binBank: "..."      # bắt buộc - binBank
  numAccBank: "..."   # bắt buộc - numAccBank
  nameAccBank: "..."  # bắt buộc - nameAccBank
  params: {}          # bắt buộc - params
  confirm: false      # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `binBank` | binBank | có | binBank (BinBankCard) |
| `numAccBank` | numAccBank | có | numAccBank (string) |
| `nameAccBank` | nameAccBank | có | nameAccBank (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="create_catalog"></a>
#### createCatalog — `zalo_call.create_catalog`

createCatalog — Tạo Danh mục sản phẩm (Catalog) mới cho Zalo Business.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.create_catalog
data:
  catalogName: "..."  # bắt buộc - catalogName
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `catalogName` | catalogName | có | catalog name (string) |

---

<a id="create_product_catalog"></a>
#### createProductCatalog — `zalo_call.create_product_catalog`

createProductCatalog — Thêm sản phẩm mới vào Danh mục sản phẩm (Product Catalog).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.create_product_catalog
data:
  catalogId: "..."       # bắt buộc - catalogId
  productName: "..."     # bắt buộc - productName
  price: "..."           # bắt buộc - price
  description: "..."     # bắt buộc - description
  files: "..."           # tuỳ chọn - files
  product_photos: "..."  # tuỳ chọn - product_photos
  params: {}             # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `catalogId` | catalogId | có | catalogId (string) |
| `productName` | productName | có | productName (string) |
| `price` | price | có | price (string) |
| `description` | description | có | description (string) |
| `files` | files | không | Upto 5 media files are allowed, will be ignored if product_photos is provided (AttachmentSource[]) |
| `product_photos` | product_photos | không | List of product photo URLs, upto 5 You can manually get the URL using `uploadProductPhoto` api (string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="delete_auto_reply"></a>
#### deleteAutoReply — `zalo_call.delete_auto_reply`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

deleteAutoReply — Xóa một kịch bản Trả lời tự động. (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.delete_auto_reply
data:
  id: "..."       # bắt buộc - id
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `id` | id | có | id of auto reply (number) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="delete_bank_account"></a>
#### deleteBankAccount — `zalo_call.delete_bank_account`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

deleteBankAccount — Xóa một tài khoản ngân hàng đã lưu. (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.delete_bank_account
data:
  accountId: "..."  # bắt buộc - accountId
  isDefault: "..."  # bắt buộc - isDefault
  confirm: false    # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `accountId` | accountId | có | accountId (number) |
| `isDefault` | isDefault | có | isDefault (boolean) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="delete_catalog"></a>
#### deleteCatalog — `zalo_call.delete_catalog`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

deleteCatalog — Xóa một Danh mục sản phẩm (Catalog). (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.delete_catalog
data:
  catalogId: "..."  # bắt buộc - catalogId
  confirm: false    # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `catalogId` | catalogId | có | catalog id (string) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="delete_conversation_label"></a>
#### deleteConversationLabel — `zalo_call.delete_conversation_label`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

deleteConversationLabel — Xóa một hoặc nhiều nhãn phân loại hội thoại (command 12165) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.delete_conversation_label
data:
  labelIds: "..."  # bắt buộc - labelIds
  params: {}       # bắt buộc - params
  confirm: false   # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `labelIds` | labelIds | có | ID hoặc danh sách ID nhãn cần xóa (number \| number[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="delete_product_catalog"></a>
#### deleteProductCatalog — `zalo_call.delete_product_catalog`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

deleteProductCatalog — Xóa một hoặc nhiều sản phẩm khỏi Danh mục sản phẩm. (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.delete_product_catalog
data:
  productIds: "..."  # bắt buộc - productIds
  catalogId: "..."   # bắt buộc - catalogId
  confirm: false     # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `productIds` | productIds | có | productIds (string \| string[]) |
| `catalogId` | catalogId | có | catalogId (string) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="delete_single_product"></a>
#### deleteSingleProduct — `zalo_call.delete_single_product`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

deleteSingleProduct — Xóa một sản phẩm đơn lẻ khỏi danh mục Zalo Business (command 12042) (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.delete_single_product
data:
  productId: "..."  # bắt buộc - productId
  catalogId: "..."  # bắt buộc - catalogId
  confirm: false    # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `productId` | productId | có | productId (string) |
| `catalogId` | catalogId | có | catalogId (string) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="get_auto_reply_list"></a>
#### getAutoReplyList — `zalo_call.get_auto_reply_list`

getAutoReplyList — Lấy danh sách các kịch bản Trả lời tự động của tài khoản.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_auto_reply_list
```

---

<a id="get_biz_account"></a>
#### getBizAccount — `zalo_call.get_biz_account`

getBizAccount — Lấy thông tin cấu hình tài khoản Zalo Business (ZBusiness).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_biz_account
data:
  friendId: "..."  # bắt buộc - friendId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `friendId` | friendId | có | The friend ID to get biz account (string) |

---

<a id="get_catalog_list"></a>
#### getCatalogList — `zalo_call.get_catalog_list`

getCatalogList — Lấy danh sách các Danh mục sản phẩm (Catalogs) của tài khoản.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_catalog_list
data:
  limit: "..."          # tuỳ chọn - limit
  lastProductId: "..."  # tuỳ chọn - lastProductId
  page: "1"             # tuỳ chọn - page
  params: {}            # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `limit` | limit | không | Number of items to retrieve (default: 20) (number) |
| `lastProductId` | lastProductId | không | lastProductId (number) |
| `page` | page | không | Page number (default: 0) (number) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="get_list_bank"></a>
#### getListBank — `zalo_call.get_list_bank`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

getListBank — Lấy danh sách mã ngân hàng (BIN / NAPAS) được Zalo hỗ trợ. (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_list_bank
data:
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="get_list_bank_account"></a>
#### getListBankAccount — `zalo_call.get_list_bank_account`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

getListBankAccount — Lấy danh sách các tài khoản ngân hàng đã lưu của người dùng. (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_list_bank_account
data:
  page: "1"       # tuỳ chọn - page
  limit: "..."    # tuỳ chọn - limit
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `page` | page | không | Page number (default: 0) (number) |
| `limit` | limit | không | Number of items to retrieve (default: 20) (number) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="get_o_a_profile"></a>
#### getOAProfile — `zalo_call.get_o_a_profile`

getOAProfile — Lấy hồ sơ chuẩn hóa đầy đủ của một Zalo Official Account (OA) theo oaId (bao gồm tích vàng isVerified, isZaloBot, dnrStatus, hotline, website, giờ mở cửa, địa chỉ, danh mục...). (chưa tự động: khong dung dich vu Zalo qua serv

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_o_a_profile
```

---

<a id="get_product_catalog_list"></a>
#### getProductCatalogList — `zalo_call.get_product_catalog_list`

getProductCatalogList — Lấy danh sách các sản phẩm nằm trong một Danh mục sản phẩm (Catalog).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_product_catalog_list
data:
  catalogId: "..."       # bắt buộc - catalogId
  limit: "..."           # tuỳ chọn - limit
  versionCatalog: "..."  # tuỳ chọn - versionCatalog
  lastProductId: "..."   # tuỳ chọn - lastProductId
  page: "1"              # tuỳ chọn - page
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `catalogId` | catalogId | có | catalogId (string) |
| `limit` | limit | không | Number of items to retrieve (default: 100) (number) |
| `versionCatalog` | versionCatalog | không | versionCatalog (number) |
| `lastProductId` | lastProductId | không | lastProductId (string) |
| `page` | page | không | Page number (default: 0) (number) |

---

<a id="get_product_detail"></a>
#### getProductDetail — `zalo_call.get_product_detail`

getProductDetail — Lấy thông tin chi tiết một sản phẩm trong danh mục Zalo Business (command 12057)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_product_detail
data:
  productId: "..."  # bắt buộc - productId
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `productId` | productId | có | ID sản phẩm cần xem (string) |

---

<a id="register_catalog"></a>
#### registerCatalog — `zalo_call.register_catalog`

registerCatalog — Đăng ký kích hoạt tính năng Danh mục sản phẩm (Catalog) cho tài khoản.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.register_catalog
data:
  enable: "..."  # bắt buộc - enable
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `enable` | enable | có | enable or disable catalog (boolean) |

---

<a id="reorder_conversation_labels"></a>
#### reorderConversationLabels — `zalo_call.reorder_conversation_labels`

reorderConversationLabels — Sắp xếp lại vị trí hiển thị của các nhãn phân loại hội thoại (command 12166)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.reorder_conversation_labels
data:
  items: "..."  # bắt buộc - items
  params: {}    # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `items` | items | có | Danh sách `{ id, offset }` theo thứ tự mới (ReorderConversationLabelEntry[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="unblock_o_a"></a>
#### unblockOA — `zalo_call.unblock_o_a`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

unblockOA — Bỏ chặn một Zalo Official Account (OA) để tiếp tục nhận tin nhắn qua /api/social/oa/unblock (cmd 12682). (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.unblock_o_a
data:
  oaId: "..."     # bắt buộc - oaId
  confirm: false  # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `oaId` | oaId | có | UID hoặc OA ID của Official Account cần bỏ chặn (string) |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="update_auto_reply"></a>
#### updateAutoReply — `zalo_call.update_auto_reply`

updateAutoReply — Cập nhật nội dung và thời gian hoạt động của kịch bản Trả lời tự động.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_auto_reply
data:
  id: "..."                         # bắt buộc - id
  content: "Họp nhóm lúc 10h sáng"  # bắt buộc - content
  isEnable: "..."                   # bắt buộc - isEnable
  startTime: "..."                  # bắt buộc - startTime
  endTime: "..."                    # bắt buộc - endTime
  scope: "..."                      # bắt buộc - scope
  uids: "..."                       # tuỳ chọn - uids
  params: {}                        # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `id` | id | có | id (number) |
| `content` | content | có | content (string) |
| `isEnable` | isEnable | có | isEnable (boolean) |
| `startTime` | startTime | có | startTime (number) |
| `endTime` | endTime | có | endTime (number) |
| `scope` | scope | có | scope (AutoReplyScope) |
| `uids` | uids | không | uids (string \| string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="update_bank_account"></a>
#### updateBankAccount — `zalo_call.update_bank_account`

> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.

updateBankAccount — Cập nhật thông tin tài khoản ngân hàng đã lưu. (không hoàn tác được)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_bank_account
data:
  accountId: "..."    # bắt buộc - accountId
  binBank: "..."      # bắt buộc - binBank
  numAccBank: "..."   # bắt buộc - numAccBank
  nameAccBank: "..."  # bắt buộc - nameAccBank
  params: {}          # bắt buộc - params
  confirm: false      # tuỳ chọn - confirm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `accountId` | accountId | có | accountId (number) |
| `binBank` | binBank | có | binBank (BinBankCard) |
| `numAccBank` | numAccBank | có | numAccBank (string) |
| `nameAccBank` | nameAccBank | có | nameAccBank (string) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |
| `confirm` | confirm | không | Đặt true để xác nhận thao tác nguy hiểm. |

---

<a id="update_catalog"></a>
#### updateCatalog — `zalo_call.update_catalog`

updateCatalog — Cập nhật tên hoặc ảnh của Danh mục sản phẩm.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_catalog
data:
  catalogId: "..."    # bắt buộc - catalogId
  catalogName: "..."  # bắt buộc - catalogName
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `catalogId` | catalogId | có | catalogId (string) |
| `catalogName` | catalogName | có | catalogName (string) |

---

<a id="update_conversation_label_item"></a>
#### updateConversationLabelItem — `zalo_call.update_conversation_label_item`

updateConversationLabelItem — Cập nhật thông tin một nhãn phân loại hội thoại và danh sách hội thoại gắn nhãn (command 12164)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_conversation_label_item
data:
  id: "..."      # bắt buộc - id
  text: "..."    # bắt buộc - text
  color: "..."   # bắt buộc - color
  offset: "..."  # bắt buộc - offset
  add: "..."     # tuỳ chọn - add
  remove: "..."  # tuỳ chọn - remove
  params: {}     # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `id` | id | có | id (number) |
| `text` | text | có | text (string) |
| `color` | color | có | color (number) |
| `offset` | offset | có | offset (number) |
| `add` | add | không | add (string[]) |
| `remove` | remove | không | remove (string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="update_product_catalog"></a>
#### updateProductCatalog — `zalo_call.update_product_catalog`

updateProductCatalog — Cập nhật thông tin chi tiết, giá bán và hình ảnh của sản phẩm trong Danh mục.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.update_product_catalog
data:
  catalogId: "..."       # bắt buộc - catalogId
  productId: "..."       # bắt buộc - productId
  productName: "..."     # bắt buộc - productName
  price: "..."           # bắt buộc - price
  description: "..."     # bắt buộc - description
  createTime: "..."      # bắt buộc - createTime
  files: "..."           # tuỳ chọn - files
  product_photos: "..."  # tuỳ chọn - product_photos
  params: {}             # bắt buộc - params
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `catalogId` | catalogId | có | catalogId (string) |
| `productId` | productId | có | productId (string) |
| `productName` | productName | có | productName (string) |
| `price` | price | có | price (string) |
| `description` | description | có | description (string) |
| `createTime` | createTime | có | createTime (number) |
| `files` | files | không | Upto 5 media files are allowed, will be ignored if product_photos is provided (AttachmentSource[]) |
| `product_photos` | product_photos | không | List of product photo URLs, upto 5 You can manually get the URL using `uploadProductPhoto` api (string[]) |
| `params` | params | có | JSON đúng như zca-js gửi (API này có biểu thức phức tạp). |

---

<a id="upload_product_photo"></a>
#### uploadProductPhoto — `zalo_call.upload_product_photo`

uploadProductPhoto — Tải ảnh sản phẩm lên máy chủ Zalo phục vụ cho Product Catalog hoặc Quick Message. (chưa tự động: tai tep len (multipart): dung khung chat/endpoint rieng cua app)

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.upload_product_photo
```

---

## Khác

<a id="voice_to_text"></a>
#### Chuyển giọng nói thành văn bản (Zalo AI) — `zalo_call.voice_to_text`

Gửi một tin nhắn thoại (URL tệp .aac/.mp3/.m4a trên máy chủ Zalo) cho Zalo AI và trả về văn bản. Chỉ dùng cho tin nhắn thoại, không phải mic trực tiếp. Kết quả cũng bắn sự kiện zalo_call_voice_to_text.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.voice_to_text
data:
  url: "..."  # bắt buộc - URL tệp ghi âm
  wait: 25    # tuỳ chọn - Chờ tối đa (giây)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `url` | URL tệp ghi âm | có | Đường dẫn tin nhắn thoại trên máy chủ Zalo (lấy từ sự kiện tin nhắn thoại). |
| `wait` | Chờ tối đa (giây) | không | Zalo AI trả kết quả bất đồng bộ; chờ tối đa ngần này giây (0 = không chờ, lấy bằng sự kiện). |

---

<a id="set_contact_tags"></a>
#### Gắn thẻ và ghi chú cho người — `zalo_call.set_contact_tags`

Gắn thẻ (ví dụ «gia đình») và ghi chú cho một người hoặc nhóm. Đặt quy tắc cho một thẻ (dịch vụ «Đặt quy tắc…», chọn «Mọi người mang một thẻ») thì tất cả người mang thẻ đó dùng quy tắc ấy, khỏi đặt từng người. Ô nào không điền thì giữ nguyên; để trống ô Thẻ là gỡ hết thẻ.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.set_contact_tags
data:
  thread_id: "6643404425553198601"  # bắt buộc - ThreadID (gõ tay)
  tags: "gia đình, người lớn tuổi"  # tuỳ chọn - Thẻ
  note: "..."                       # tuỳ chọn - Ghi chú
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | ThreadID (gõ tay) | có | ID Zalo của người hoặc nhóm. Lấy danh sách bằng dịch vụ list_contacts. |
| `tags` | Thẻ | không | Các thẻ cách nhau bằng dấu phẩy, ví dụ gia đình, người lớn tuổi. Tối đa 10 thẻ, không phân biệt hoa thường. |
| `note` | Ghi chú | không | Ghi chú ngắn về người này (tối đa 500 ký tự). |

---
