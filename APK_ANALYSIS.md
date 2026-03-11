# MOL3 APK Analysis — Formuler Z11 Pro MAX

## Overview
- **Package:** tv.formuler.mol3.real
- **Size:** 103 MB
- **Architecture:** armeabi-v7a (32-bit ARM)
- **Player:** VLC (libvlc.so) + FFmpeg (libffmpegJNI.so)
- **Auth:** SiptvJni native lib (libSiptvJni.so) — Stalker portal via curl

## Protocols

### 1. Stalker Portal API (primary)
The app communicates with IPTV servers via the Stalker middleware protocol.
Authentication is handled in native code (libSiptvJni.so).

Key API endpoints:
```
?action=get_all_channels&type=itv                       # All live channels
?action=get_ordered_list&category=X&type=itv&p=N        # Paginated channel list
?action=get_categories&type=X                           # Category list
?action=get_genres&type=itv                             # Genre list  
?action=get_short_epg&ch_id=X                           # Channel EPG
?action=get_epg_info&period=X                           # Full EPG
?action=get_ordered_list&movie_id=X                     # VOD details
?action=get_ordered_list&movie_id=0&season_id=0&episode_id=0&category=X  # Series
?action=create_link&type=X&cmd=X                        # Get playback URL
?action=confirm_event&type=watchdog&event_active_id=X   # Keepalive
```

### 2. XtreamCodes API (alternative)
Standard XtreamCodes compatible player API:
```
player_api.php?action=get_live_streams&username=X
player_api.php?action=get_vod_streams
player_api.php?action=get_vod_categories
player_api.php?action=get_vod_info
player_api.php?action=get_series
player_api.php?action=get_series_categories
player_api.php?action=get_series_info
player_api.php?action=get_short_epg
player_api.php?action=get_simple_data_table
```

### 3. TMDb API
Used for metadata enrichment: `https://api.themoviedb.org/3/`
Fetches: details, credits, images, videos for movies/series.

## Internal Database Structure

### Server Configuration
```sql
server (server_id, server_type, enable, name, url, user_id, password, 
        epg_offset, user_mac, user_serial, play_user_agent, api_user_agent, 
        expire_status, expire_time, playlist_vod_url, playlist_epg_url1-5, ...)

portal_account (server_id, account_type, server_addr, device_id1, device_id2,
                token, portal_path, portal_index, portal_ver, sign, 
                phpSessionId, cookie_name, cookie_value, xpc_mac, xpc_sn,
                vod_path, mac, sn, user_id, password, ...)
```

### Content
```sql
channels (number, channel_key, server_id, channel_type, stream_id, name,
          stream_logo, play_url, xmltv_id, group_id, tv_archive, pvr, is_adult)

contents (number, content_key, server_id, vod_type, vod_id, vod_name,
          group_id, poster, genres, director, actors, description, duration,
          year, rating, o_name, cmd, stream_type, container_extension, 
          backdrop_path, youtube_trailer)

groups (number, group_key, server_id, channel_type, group_id, group_name, is_adult)
```

### Favorites & History
```sql
favorite (protocol, server_id, category_id, stream_type, stream_id, vod_name,
          poster, genres, description, duration, year, rating, season_count, 
          episode_count, ...)

favorite_channel (number, favorite_group_id, server_id, channel_type, stream_id,
                  group_id, position, display_number, name, stream_logo, is_adult)

favorite_season (protocol, server_id, category_id, stream_type, stream_id,
                 season_number, episode_count, new_added, user_confirm, update_time_ms)

history (protocol, server_id, category_id, stream_type, stream_id, season_id,
         episode_id, vod_name, poster, genres, description, season_num, episode_num,
         episode_plot, episode_duration, episode_rating, episode_extension,
         playback_position, playback_duration, record_time)
```

### Other Tables
```sql
epg (epg_key, server_id, stream_id, epg_name, epg_desc, start_time_ms, end_time_ms, is_catchup)
search_content (type, _id, suggest_intent_extra_data, suggest_text_1, suggest_text_2, ...)
WatchlistDaoItem (id, channel_name, epg_name, epg_start_time_ms, epg_end_time_ms, ...)
AlarmDaoItem (alarmId, alarm_start_time_ms, channel_name, epg_name, ...)
sports_alarm (alarm_id, competition_id, teams, venue, round_name, ...)
words (query, recordedTimeMs) -- search history
```

## Intent Extras

### SchemeLinkActivity (Deeplink Handler)
```
# Live Channel
i.channel_type=5
S.group_id=32768_0_0
S.unique_channel_id=0_1040_18800_0

# VOD
S.vod_unique_id=stalker://tv.formuler.stream?server_id=0&category_id=X&stream_type=movie&stream_id=X
i.channel_type=3  (favorites) / 1 (history)

# Series
S.vod_id=X
S.vod_unique_id=stalker://tv.formuler.stream?server_id=0&category_id=X&stream_type=tv&stream_id=X&season_id=X:S&episode_id=E
i.channel_type=4  (favorites) / 2 (history)
```

### Additional Extras (discovered in APK)
```
tv.formuler.intent.extra.EXTRA_ASK_RESUME_PLAYBACK     # Resume from last position
tv.formuler.mol3.extra.EXTRA_SELECTED_STREAM_TYPE       # Stream type selection
tv.formuler.mol3.extra.EXTRA_SELECTED_STREAM_DETAIL     # Stream detail data
tv.formuler.mol3.extra.EXTRA_SELECTED_STREAM_EPISODE    # Episode selection
tv.formuler.mol3.extra.EXTRA_SELECTED_STREAM_QUALITY    # Quality selection
tv.formuler.mol3.EXTRA_SEASON_NUMBER                    # Season number
tv.formuler.mol3.EXTRA_EPISODE_NUMBER                   # Episode number
tv.formuler.mol3.EXTRA_DEFAULT_SEARCH_TEXT              # Pre-fill search text
tv.formuler.mol3.intent.extra.EXTRA_SEARCH_MODULE_ID    # Search module filter
tv.formuler.mol3.intent.extra.EXTRA_SEARCH_INITIAL_SEARCH  # Auto-search on launch
tv.formuler.intent.extra.EXTRA_SELECTED_URI_STRING      # Direct playback URI
tv.formuler.intent.extra.EXTRA_SELECTED_URI_NAME        # URI display name
tv.formuler.intent.extra.EXTRA_SELECTED_URI_USER_AGENT  # Custom user agent
tv.formuler.intent.extra.EXTRA_HISTORY                  # History context
tv.formuler.mol3.extra.EXTRA_RECENT_CATEGORY            # Recent category
tv.formuler.mol3.extra.EXTRA_RECENT_IDENTIFIER          # Recent identifier
```

## Player Preferences
```
pref_settings_player_playback_resume     # Resume on/off
pref_settings_player_buffer_time         # Buffer size
pref_settings_player_retry_count         # Retry count
pref_settings_player_retry_interval      # Retry interval
pref_settings_player_afr_live_enabled    # Auto frame rate (live)
pref_settings_player_afr_vod_enabled     # Auto frame rate (VOD)
pref_settings_player_afr_series_enabled  # Auto frame rate (series)
pref_settings_player_afr_scale_up        # AFR scale up
pref_settings_player_external_vod_player # External player
pref_settings_player_metadata_api_enabled # TMDb metadata
pref_settings_player_trailer_player      # Trailer player
```

## MOL Management Server
- **URL:** https://molm.aloys.co.kr
- **Sports:** https://sports.aloys.co.kr
- **Auth:** /api/auth/signup/device
- **Relay:** /api/v1/relay
- **Sports:** /api/v1/sports/

## Key Observations

1. **No root needed for content provider** — favorites/history accessible via `content://formuler.media.tv/preview_program`
2. **Internal DB inaccessible** — server credentials, full channel list, and playback positions require root or backup
3. **VLC-based player** — supports external player option, custom user agents
4. **Stalker protocol** — industry standard for IPTV middleware, well documented
5. **Resume support** — EXTRA_ASK_RESUME_PLAYBACK intent extra available
6. **Quality selection** — EXTRA_SELECTED_STREAM_QUALITY intent extra available
7. **Direct URI playback** — EXTRA_SELECTED_URI_STRING can play arbitrary URLs

## Service Package (tv.formuler.service.real)

### IFormulerService AIDL Interface (complete)

**Media Control:**
```
play, pause, stop, seekTo, fastForward, rewind
next, previous
playFromMediaId, playFromSearch, playFromUri
prepare, prepareFromMediaId, prepareFromSearch, prepareFromUri
getPlaybackState
adjustVolume, setVolumeTo
send, sendCommand, sendCustomAction, sendMediaButton
```

**Power Management:**
```
appPowerControl, setPowerMode, getPowerMode
getPrePowerState, setPrePowerState
softwareReset
```

**System:**
```
factoryReset
appSetProperty, appSystemFunc, appSysReadFile
appCpuRepair
appGetBootReason, getBootReasonWakeupSrc
changePincode, checkPincode, getMasterPincode, setMasterPincode
changeState, getAppState
getRecStatus, setRecStatus
isChanghongFactory, appSysIsFactoryMode, appSysSetFactoryFlag
```

### Broadcast Receivers
```
MolReceiver:
  - fserver_restart        → Restart streaming server connection
  - ACTION_ALARM_GOTO_LIVE → Switch to live TV
  - ACTION_ALARM_FIRE      → Fire alarm

AlarmReceiver:
  - tv.formuler.mol3.alarm.ACTION_ALARM_WAKEUP
  - tv.formuler.mol3.alarm.watchlist.ACTION_WATCHLIST_ON_TIME

SportsAlarmReceiver:
  - tv.formuler.mol3.sports.ACTION_ALARM

PreviewChannelReceiver:
  - android.media.tv.action.PREVIEW_PROGRAM_BROWSABLE_DISABLED
  - android.media.tv.action.INITIALIZE_PROGRAMS  → Force refresh preview channels
```

### Launchable Activities (Service Package)
```
AutoShutdownActivity — Power-off countdown dialog (has intent filter)
  - Can be used for sleep timer functionality
DialogActivity — System dialog (DIALOG_TYPE_REC_POWER_CONFIRM for recording+power)
StkMessageActivity — Display STK portal messages
SystemMessageActivity — Authentication/system messages
```

### ExternalMessageService
- Handles STK portal notifications from IPTV server
- Requires permission: `tv.formuler.service.permssion.EXTERNAL_MESSAGE`
- Message types: MSG_TYPE1_GENERATED, MSG_TYPE2_RECEVIED, MSG_TYPE3_GENERATED

### TVService Bindings
```
tv.formuler.service.START_TV_SERVICE    → Start the TV service
tv.formuler.service.BIND_TV_SERVICE     → Bind to TV service
tv.formuler.service.BIND_TV_SERVICE_MOL → Bind from MOL3 app
```

## Network
- Management: molm.aloys.co.kr, sports.aloys.co.kr (Akamai CDN)
- Firebase/GMS connections when idle
- Streaming connections only active during playback

## ActionCard Detail Page Buttons
The VOD/series detail overlay can show these action buttons:
```
Watch (DefaultWatch, ExternalWatch)              → Play from start
Continue (WatchContinue, EpisodeContinue,         → Resume from last position
          QualityContinue, QualityEpisodeContinue)
Restart (WatchRestart, EpisodeRestart,            → Restart from beginning
         QualityRestart, QualityEpisodeRestart)
AllEpisodes (Default, External)                   → Episode browser
ChooseQuality (Default, External)                 → Quality picker
Favorite                                          → Toggle favorite
```
