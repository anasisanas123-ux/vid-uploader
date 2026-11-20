# Shorts & Reels Uploader – Setup Guide

Upload one vertical video to **YouTube Shorts**, **Instagram Reels** and **Facebook Reels** at the same time, with a separate caption for each and optional scheduling.

Everything runs on your PC. Your login tokens are saved in `data/tokens.json` and your videos in `media/`.

---

## 1. Start the app

Double-click **`run.bat`**. It opens <http://localhost:8000> in your browser.

The Connect buttons stay greyed out until you add your keys (steps 3–4). After editing `.env`, close the black window and run `run.bat` again.

---

## 2. Prepare your Instagram account (one-time, ~2 minutes)

Instagram only allows API posting from **Professional** accounts that are **linked to a Facebook Page**.

1. Instagram app → **Settings → Account type and tools → Switch to professional account**. Choose **Creator** or **Business**. Both are free.
2. If you don't have a Facebook Page, create one at <https://www.facebook.com/pages/create>.
3. Link them: Facebook Page → **Settings → Linked accounts → Instagram → Connect account**.
   (Or in Instagram: **Settings → Accounts Center** → add your Facebook account and Page.)

---

## 3. YouTube – Google Cloud keys (~10 minutes)

1. Go to <https://console.cloud.google.com/> → create a new project (e.g. "My Uploader").
2. **APIs & Services → Library** → search **YouTube Data API v3** → **Enable**.
3. **APIs & Services → OAuth consent screen** (or "Google Auth Platform"):
   - User type: **External** → fill in the app name and your email.
   - **Audience / Test users** → **add your own Google account** (the one that owns the YouTube channel).
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**
   - Application type: **Web application**
   - Authorized redirect URI: `http://localhost:8000/auth/youtube/callback`
5. Copy the **Client ID** and **Client secret** into `.env`:
   ```
   GOOGLE_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=xxxxxxxx
   ```
6. Restart the app → **Connect** next to YouTube → sign in. If you see "Google hasn't verified this app", click **Continue**. It's your own app.

### ⚠ Important YouTube limitations
- **Videos are private until your project is audited.** Google locks videos uploaded through new, unaudited API projects to **private**. To post publicly, submit the free audit form: <https://support.google.com/youtube/contact/yt_api_form>. Approval usually takes a few days to a few weeks. Until then you can upload, then switch the video to Public yourself in YouTube Studio.
- **Daily limit:** each upload costs about 1,600 of your 10,000 free daily quota units, so about **6 uploads a day**. The audit form can also raise this.
- **Weekly reconnect while in "Testing":** while the consent screen is in *Testing* mode, Google expires your login after 7 days. To avoid this, set the OAuth consent screen to **In production**. You'll see an "unverified app" warning when you sign in, which is fine for personal use.

---

## 4. Facebook + Instagram – Meta app keys (~10 minutes)

1. Go to <https://developers.facebook.com/> → **My Apps → Create App**.
2. Pick the use case(s) for managing **Pages** content and **Instagram** content (titles look like "Manage everything on your Page" and "Manage messaging & content on Instagram"). If asked for an app type, choose **Business**.
3. Make sure these permissions are added (under **Use cases → Customize**, or **App Review → Permissions**):
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `business_management`, `instagram_basic`, `instagram_content_publish`
4. **App settings → Basic**: copy the **App ID** and **App secret** into `.env`:
   ```
   META_APP_ID=1234567890
   META_APP_SECRET=xxxxxxxx
   ```
5. Redirect URI: in **Facebook Login (for Business) → Settings → Valid OAuth Redirect URIs**, add
   `http://localhost:8000/auth/meta/callback`
   (Localhost is usually allowed automatically while the app is in Development mode.)
6. **Only if your app has "Facebook Login for Business"** (not plain "Facebook Login"):
   go to **Facebook Login for Business → Configurations → Create configuration**, choose *User access token*, tick the permissions above, then copy the **Configuration ID** into `.env` as `META_CONFIG_ID=...`.
7. Restart the app → **Connect** next to Facebook + Instagram. When Facebook asks, **select your Page AND your Instagram account** and allow all permissions.

Keep the app in **Development mode**. As the app's admin you can post to your own Page and Instagram without Meta's App Review.

The Page connection doesn't expire. If you change your Facebook password, click Connect again.

---

## 5. Using it

1. Drop in a vertical video (9:16 MP4, H.264).
2. Write your caption → **Copy to all platforms** → adjust each one (e.g. different hashtags).
3. Tick the platforms → **Post now** or **Schedule** → **Upload**.
4. The **Uploads** panel shows live progress, a **View ↗** link when done, and **Retry** if something fails.

**Scheduled posts only go out while the app is running.** Leave `run.bat` open, or add it to Windows Startup (`Win+R` → `shell:startup` → put a shortcut to `run.bat` there).

### Platform limits

| | YouTube Shorts | Instagram Reels | Facebook Reels |
|---|---|---|---|
| Length | up to 3 min | 3 s – 15 min | 3 s – 90 s |
| Caption | title 100 chars, description 5000 | 2200 chars, 30 hashtags | – |
| Daily | ~6 uploads (API quota) | 50 posts / 24 h | – |

**Best format for all three:** 1080×1920, 9:16, MP4/H.264, **under 90 seconds**.

Optional: install FFmpeg (`winget install ffmpeg`). The app will then also check resolution, codec and length on the server side.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Connect button greyed out | Keys are missing from `.env` → restart `run.bat` after editing |
| `redirect_uri_mismatch` (Google) | The redirect URI in Google Cloud must be exactly `http://localhost:8000/auth/youtube/callback` |
| "No Facebook Pages found" | Create a Page, and tick it during the Facebook login screen |
| "Instagram: not linked to this Page" | Do step 2.3, then click Disconnect → Connect again |
| YouTube video is private | Expected until your API audit is approved (see step 3) |
| `quotaExceeded` | YouTube daily limit reached; it resets at midnight Pacific time |
| Instagram "could not process the video" | Re-export as MP4 H.264 + AAC audio, 9:16, under 15 min |
