# API Setup Guide for Hybrid Genre Fetcher

## 🎵 Spotify Web API (FREE - Recommended)

### Setup Steps:
1. Go to https://developer.spotify.com/dashboard
2. Click "Create App"
3. Fill in:
   - **App Name**: "Music Genre Tagger"
   - **App Description**: "Personal music library genre tagging"
   - **Website**: http://localhost (can be anything)
   - **Redirect URIs**: `https://example.com/callback` (required but won't be used)
   - **API/SDKs**: Check "Web API"
   
   **Note**: Even though we enter a redirect URI, we won't use it since we're only accessing public metadata with Client Credentials flow.
4. Click "Save"
5. Copy your **Client ID** and **Client Secret**

### Expected Results:
- **Coverage**: 90%+ of mainstream artists
- **Genre Quality**: Excellent (curated by Spotify)
- **Rate Limits**: 30,000 requests/month (very generous)

---

## 🎧 Last.fm API (FREE)

### Setup Steps:
1. Go to https://www.last.fm/api/account/create
2. Fill in:
   - **Application Name**: "Music Genre Tagger"
   - **Description**: "Personal music library organization"
   - **Application Homepage**: http://localhost
   - **Contact Email**: your email
3. Submit application
4. Copy your **API Key**

### Expected Results:
- **Coverage**: Good for popular music
- **Genre Quality**: Community-driven (variable)
- **Rate Limits**: 5 requests/second

---

## 💿 Discogs API (FREE)

### Setup Steps:
1. Create account at https://www.discogs.com/
2. Go to https://www.discogs.com/settings/developers
3. Click "Generate new token"
4. **Application Name**: "Music Genre Tagger"
5. Copy your **Personal Access Token**

### Expected Results:
- **Coverage**: Excellent for rare/vinyl/detailed releases
- **Genre Quality**: Very detailed styles and subgenres
- **Rate Limits**: 1000 requests/day (240/minute)

---

## 🌐 Deezer API (No Key Required)
- Already working in the system
- **Coverage**: Good European focus
- **Genre Quality**: Basic but reliable
- **Rate Limits**: Fair use policy

---

## 🏆 Premium APIs for Consideration

### Gracenote (Sony Music Entertainment)
- **Contact**: https://developer.gracenote.com/
- **Pricing**: Enterprise (typically $5,000-$50,000+/year)
- **Quality**: Industry gold standard
- **Coverage**: Most comprehensive database
- **Use Case**: Professional applications, major labels

### AllMusic/Rovi (TiVo)
- **Contact**: https://www.tivo.com/developer
- **Pricing**: Commercial licensing required
- **Quality**: Professional music journalism curation
- **Coverage**: Detailed genre analysis and reviews

### MusicGraph API
- **Status**: Discontinued (acquired by Pandora)
- **Alternative**: Use Pandora's Music Genome Project data

### 7digital API
- **Contact**: https://docs.7digital.com/
- **Pricing**: Commercial tiers available
- **Quality**: Good commercial metadata
- **Coverage**: Mainstream releases focus

---

## 📊 Expected Multi-Source Results

With all free APIs configured, you should see:

**Before (Deezer only):**
- 60% match rate
- Basic genres only
- Low confidence scores

**After (Spotify + Last.fm + Discogs + Deezer):**
- 85-90% match rate
- Detailed genre hierarchies
- High confidence through cross-validation
- Better handling of obscure artists

**Example Multi-Source Result:**
```
Pink Floyd - The Dark Side of the Moon
Sources: spotify, discogs, lastfm, deezer
Genres: Progressive Rock; Psychedelic Rock; Rock; Art Rock
Confidence: 94% (4 sources agree)
```

---

## 🔧 Configuration Template

Copy this into your `api_config.json`:

```json
{
  "spotify": {
    "client_id": "YOUR_SPOTIFY_CLIENT_ID_HERE",
    "client_secret": "YOUR_SPOTIFY_CLIENT_SECRET_HERE",
    "enabled": true
  },
  "musicbrainz": {
    "user_agent": "MusicGenreTagger/2.0",
    "enabled": true
  },
  "lastfm": {
    "api_key": "YOUR_LASTFM_API_KEY_HERE",
    "enabled": true
  },
  "discogs": {
    "token": "YOUR_DISCOGS_TOKEN_HERE",
    "enabled": true
  },
  "deezer": {
    "enabled": true
  },
  "gracenote": {
    "client_id": "",
    "client_tag": "",
    "user_id": "",
    "enabled": false
  },
  "allmusic": {
    "api_key": "",
    "enabled": false
  }
}
```

---

## ⚡ Quick Test Commands

After setting up APIs:

```bash
# Test the hybrid fetcher
python3 hybrid_genre_fetcher.py

# Test with your actual music library
python3 music_genre_tagger.py /Volumes/T7/Albums batch --dry-run --limit 5 --confidence 80
```