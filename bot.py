import os
import logging
import asyncio
import json
import random
import string
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from io import BytesIO
import traceback

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    BotCommand,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputFile
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    ContextTypes, 
    filters,
    ConversationHandler
)
from telegram.error import BadRequest

import yt_dlp
import requests
from bs4 import BeautifulSoup
import re

# ======================
# CONFIGURATION
# ======================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

# Fake Premium System (No Real Payment)
class PremiumConfig:
    # Fake premium users (you can add users manually)
    FAKE_PREMIUM_USERS = []  # Add user IDs here if you want
    
    # Daily limits
    FREE_DAILY_LIMIT = 10
    PREMIUM_DAILY_LIMIT = 50
    
    # File size limits (in bytes)
    FREE_MAX_SIZE = 50 * 1024 * 1024  # 50MB
    PREMIUM_MAX_SIZE = 200 * 1024 * 1024  # 200MB
    
    # Quality limits
    FREE_MAX_QUALITY = "720p"
    PREMIUM_MAX_QUALITY = "4K"
    
    # Referral system
    REFERRAL_BONUS = 5  # Extra downloads per referral
    
    # VIP Codes (share with friends)
    VIP_CODES = {
        "WELCOME2024": 30,  # code: days_of_premium
        "VIPACCESS": 60,
        "YOUTUBER": 90,
        "INFLUENCER": 180,
        "DEVIL": 365  # 👑 Special code
    }

# ======================
# LOGGING SETUP
# ======================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# DATABASE SIMULATION (Using JSON files)
# ======================
class CoolDatabase:
    def __init__(self):
        self.users_file = "users.json"
        self.stats_file = "stats.json"
        self.downloads_file = "downloads.json"
        self._init_files()
    
    def _init_files(self):
        """Initialize JSON files"""
        for file in [self.users_file, self.stats_file, self.downloads_file]:
            if not os.path.exists(file):
                with open(file, 'w') as f:
                    json.dump({}, f)
    
    def get_user(self, user_id: int) -> Dict:
        """Get user data"""
        try:
            with open(self.users_file, 'r') as f:
                users = json.load(f)
            return users.get(str(user_id), self._create_default_user(user_id))
        except:
            return self._create_default_user(user_id)
    
    def update_user(self, user_id: int, data: Dict):
        """Update user data"""
        try:
            with open(self.users_file, 'r') as f:
                users = json.load(f)
            
            user_id_str = str(user_id)
            if user_id_str not in users:
                users[user_id_str] = self._create_default_user(user_id)
            
            users[user_id_str].update(data)
            users[user_id_str]['updated_at'] = datetime.now().isoformat()
            
            with open(self.users_file, 'w') as f:
                json.dump(users, f, indent=2)
        except Exception as e:
            logger.error(f"Update user error: {e}")
    
    def _create_default_user(self, user_id: int) -> Dict:
        """Create default user structure"""
        return {
            "user_id": user_id,
            "is_premium": False,
            "premium_until": None,
            "daily_downloads": 0,
            "total_downloads": 0,
            "referral_code": self._generate_referral_code(),
            "referrals": [],
            "redeemed_codes": [],
            "join_date": datetime.now().isoformat(),
            "last_reset": datetime.now().date().isoformat()
        }
    
    def _generate_referral_code(self) -> str:
        """Generate random referral code"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    def reset_daily_counts(self):
        """Reset daily download counts"""
        try:
            today = datetime.now().date().isoformat()
            with open(self.users_file, 'r') as f:
                users = json.load(f)
            
            for user_id, user_data in users.items():
                if user_data.get('last_reset') != today:
                    user_data['daily_downloads'] = 0
                    user_data['last_reset'] = today
            
            with open(self.users_file, 'w') as f:
                json.dump(users, f, indent=2)
        except Exception as e:
            logger.error(f"Reset counts error: {e}")

# Initialize database
db = CoolDatabase()

# ======================
# VIDEO DOWNLOADER
# ======================
class VideoDownloader:
    def __init__(self):
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
            'http_chunk_size': 10485760,
        }
    
    async def get_video_info(self, url: str) -> Dict:
        """Get video information"""
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                formats = []
                for fmt in info.get('formats', []):
                    if fmt.get('vcodec') != 'none' or fmt.get('acodec') != 'none':
                        formats.append({
                            'format_id': fmt['format_id'],
                            'ext': fmt.get('ext', 'mp4'),
                            'resolution': fmt.get('resolution', 'N/A'),
                            'height': fmt.get('height', 0),
                            'width': fmt.get('width', 0),
                            'filesize': fmt.get('filesize', 0),
                            'quality': f"{fmt.get('height', 0)}p" if fmt.get('height') else 'Audio',
                            'note': fmt.get('format_note', '')
                        })
                
                return {
                    'success': True,
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                    'like_count': info.get('like_count', 0),
                    'formats': formats,
                    'webpage_url': info.get('webpage_url', url),
                    'extractor': info.get('extractor', 'generic'),
                    'description': info.get('description', '')[:500]
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def download_video(self, url: str, format_id: str = "best") -> Tuple[bool, str, str]:
        """Download video"""
        try:
            opts = self.ydl_opts.copy()
            opts['format'] = format_id
            opts['outtmpl'] = 'downloads/%(title)s.%(ext)s'
            
            # Create downloads directory
            os.makedirs('downloads', exist_ok=True)
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                # Check if file exists
                if not os.path.exists(filename):
                    # Try with different extension
                    for ext in ['.webm', '.mkv', '.mp4', '.m4a', '.mp3']:
                        alt_filename = filename.rsplit('.', 1)[0] + ext
                        if os.path.exists(alt_filename):
                            filename = alt_filename
                            break
                
                return True, filename, info.get('title', 'video')
        except Exception as e:
            return False, "", str(e)
    
    async def download_audio(self, url: str) -> Tuple[bool, str, str]:
        """Download audio only"""
        try:
            opts = self.ydl_opts.copy()
            opts['format'] = 'bestaudio/best'
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
            opts['outtmpl'] = 'downloads/%(title)s.%(ext)s'
            
            os.makedirs('downloads', exist_ok=True)
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                filename = filename.rsplit('.', 1)[0] + '.mp3'
                
                return True, filename, info.get('title', 'audio')
        except Exception as e:
            return False, "", str(e)

# ======================
# MAIN BOT CLASS
# ======================
class CoolVideoBot:
    def __init__(self):
        self.downloader = VideoDownloader()
        self.user_cache = {}
        
        # Bot commands list
        self.commands = [
            ("start", "🚀 Start the bot"),
            ("help", "📚 Show all commands"),
            ("premium", "👑 Premium features info"),
            ("myplan", "📊 Check your current plan"),
            ("download", "⬇️ Download video from URL"),
            ("ytdl", "🎬 Download YouTube video"),
            ("tiktok", "💃 Download TikTok video"),
            ("insta", "📸 Download Instagram video"),
            ("twitter", "🐦 Download Twitter video"),
            ("facebook", "📘 Download Facebook video"),
            ("audio", "🎵 Extract audio from video"),
            ("batch", "📦 Batch download (Premium)"),
            ("compress", "🗜️ Compress video (Premium)"),
            ("convert", "🔄 Convert format (Premium)"),
            ("info", "ℹ️ Get video information"),
            ("search", "🔍 Search videos (Premium)"),
            ("trending", "🔥 Trending videos"),
            ("history", "📜 Your download history"),
            ("stats", "📈 Your statistics"),
            ("refer", "👥 Refer & earn bonus"),
            ("vip", "🎟️ Redeem VIP code"),
            ("support", "💬 Contact support"),
            ("feedback", "💡 Send feedback"),
            ("settings", "⚙️ Bot settings"),
            ("language", "🌐 Change language"),
            ("donate", "❤️ Support development"),
            ("about", "ℹ️ About this bot"),
            ("terms", "📜 Terms of service"),
            ("admin", "🛠️ Admin panel"),
        ]
    
    # ======================
    # HELPER FUNCTIONS
    # ======================
    def is_premium_user(self, user_id: int) -> bool:
        """Check if user is premium"""
        user_data = db.get_user(user_id)
        
        # Check fake premium list
        if user_id in PremiumConfig.FAKE_PREMIUM_USERS:
            return True
        
        # Check premium until date
        premium_until = user_data.get('premium_until')
        if premium_until:
            try:
                premium_date = datetime.fromisoformat(premium_until)
                if premium_date > datetime.now():
                    return True
            except:
                pass
        
        return False
    
    def can_download(self, user_id: int) -> Tuple[bool, str]:
        """Check if user can download"""
        user_data = db.get_user(user_id)
        is_premium = self.is_premium_user(user_id)
        
        # Reset daily counts if needed
        today = datetime.now().date().isoformat()
        if user_data.get('last_reset') != today:
            user_data['daily_downloads'] = 0
            user_data['last_reset'] = today
            db.update_user(user_id, user_data)
        
        daily_limit = PremiumConfig.PREMIUM_DAILY_LIMIT if is_premium else PremiumConfig.FREE_DAILY_LIMIT
        
        if user_data.get('daily_downloads', 0) >= daily_limit:
            reset_time = "tomorrow"
            return False, f"⚠️ Daily limit reached! ({daily_limit} downloads/day)\nReset: {reset_time}"
        
        return True, ""
    
    def update_download_count(self, user_id: int):
        """Update user download count"""
        user_data = db.get_user(user_id)
        current = user_data.get('daily_downloads', 0)
        total = user_data.get('total_downloads', 0)
        
        db.update_user(user_id, {
            'daily_downloads': current + 1,
            'total_downloads': total + 1
        })
    
    def format_duration(self, seconds: int) -> str:
        """Format duration"""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds//60}:{seconds%60:02d}"
        else:
            return f"{seconds//3600}:{(seconds%3600)//60:02d}:{seconds%60:02d}"
    
    def format_size(self, bytes_size: int) -> str:
        """Format file size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} TB"
    
    # ======================
    # COMMAND HANDLERS
    # ======================
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command with awesome welcome"""
        user = update.effective_user
        is_premium = self.is_premium_user(user.id)
        
        # Cool ASCII art
        welcome_text = f"""
╔══════════════════════════════════╗
║   🚀 *PREMIUM VIDEO DOWNLOADER*  ║
╚══════════════════════════════════╝

✨ *Welcome {user.first_name}!* ✨

🎮 *Your Status:* {"👑 **VIP PREMIUM**" if is_premium else "🎯 **PRO USER**"}

🔥 *What I Can Do:*
• 📥 Download from 1000+ sites
• 🎵 Extract audio (MP3)
• 🎞️ 4K Ultra HD quality
• ⚡ Lightning fast speed
• 📦 Batch downloads
• 🛡️ Virus protection
• 🌐 All formats supported

🎁 *Free Features:*
• {PremiumConfig.FREE_DAILY_LIMIT} downloads/day
• {self.format_size(PremiumConfig.FREE_MAX_SIZE)} file limit
• {PremiumConfig.FREE_MAX_QUALITY} max quality
• Basic support

👑 *Premium Features:*
• {PremiumConfig.PREMIUM_DAILY_LIMIT} downloads/day
• {self.format_size(PremiumConfig.PREMIUM_MAX_SIZE)} file limit
• {PremiumConfig.PREMIUM_MAX_QUALITY} max quality
• Priority processing
• No ads
• VIP support

📌 *Quick Start:*
1. Send any video URL
2. Select quality
3. Download! 🎉

⚡ *Pro Tips:*
• Use /premium for VIP codes
• Use /refer for bonus downloads
• Use /batch for multiple videos

Type /help for all commands!
"""
        
        keyboard = [
            [InlineKeyboardButton("⬇️ Download Video", callback_data="download_guide")],
            [InlineKeyboardButton("👑 Get Premium", callback_data="premium_info")],
            [InlineKeyboardButton("📚 All Commands", callback_data="help_menu")],
        ]
        
        if is_premium:
            keyboard.append([InlineKeyboardButton("🎮 VIP Dashboard", callback_data="vip_dashboard")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show all commands in cool format"""
        user = update.effective_user
        is_premium = self.is_premium_user(user.id)
        
        help_text = """
╔══════════════════════════════════╗
║        📚 *ALL COMMANDS*         ║
╚══════════════════════════════════╝

🎮 *BASIC COMMANDS:*
/start - Start bot
/help - This menu
/download [url] - Download video
/audio [url] - Extract audio
/info [url] - Video information
/myplan - Check your plan
/stats - Your statistics
/history - Download history

🎬 *PLATFORM SPECIFIC:*
/ytdl [url] - YouTube
/tiktok [url] - TikTok
/insta [url] - Instagram
/twitter [url] - Twitter
/facebook [url] - Facebook

👑 *PREMIUM FEATURES:* """
        
        if is_premium:
            help_text += """✅ UNLOCKED
/batch - Multiple videos
/compress - Reduce size
/convert - Change format
/search - Find videos
"""
        else:
            help_text += """🔒 LOCKED (Get VIP)
/batch - Multiple videos 🔒
/compress - Reduce size 🔒
/convert - Change format 🔒
/search - Find videos 🔒
"""
        
        help_text += """
🎁 *BONUS FEATURES:*
/premium - VIP information
/refer - Referral program
/vip [code] - Redeem code
/trending - Hot videos
/support - Get help
/feedback - Send suggestions
/donate - Support us
/about - About bot
/terms - Terms of service

🛠️ *ADMIN COMMANDS:* """
        
        if user.id in ADMIN_IDS:
            help_text += """✅ UNLOCKED
/admin - Admin panel
/broadcast - Send message
/users - View all users
/statsall - All statistics
"""
        else:
            help_text += "🔒 LOCKED\n"
        
        help_text += "\n⚡ *Tip:* Just send any video URL to download!"
        
        keyboard = [
            [InlineKeyboardButton("🎮 Quick Start Guide", callback_data="quick_guide")],
            [InlineKeyboardButton("👑 Get Premium", callback_data="premium_info")],
            [InlineKeyboardButton("📥 Download Now", switch_inline_query_current_chat="")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            help_text,
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    
    async def premium_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show premium information with VIP codes"""
        user = update.effective_user
        is_premium = self.is_premium_user(user.id)
        
        premium_text = f"""
╔══════════════════════════════════╗
║         👑 *VIP PREMIUM*         ║
╚══════════════════════════════════╝

{'🎉 *YOU ARE PREMIUM USER!* 🎉' if is_premium else '🎯 *UPGRADE TO PREMIUM* 🎯'}

✨ *Premium Benefits:*
• ⚡ {PremiumConfig.PREMIUM_DAILY_LIMIT} downloads/day (10x more!)
• 🎞️ {PremiumConfig.PREMIUM_MAX_QUALITY} Ultra HD
• 📦 {self.format_size(PremiumConfig.PREMIUM_MAX_SIZE)} file size
• 🚀 Priority processing
• 📦 Batch downloads
• 🛡️ No ads
• 👑 VIP badge
• 💬 Priority support

🎮 *How to Get Premium:*

1. *VIP CODES:* (Limited time!)
"""
        
        # Show available VIP codes
        user_data = db.get_user(user.id)
        redeemed = user_data.get('redeemed_codes', [])
        
        for code, days in PremiumConfig.VIP_CODES.items():
            if code in redeemed:
                premium_text += f"   ✅ `{code}` - {days} days (Used)\n"
            else:
                premium_text += f"   🎁 `{code}` - {days} days free!\n"
        
        premium_text += f"""
2. *REFERRAL PROGRAM:*
   Invite friends using /refer
   Each referral = {PremiumConfig.REFERRAL_BONUS} extra downloads!

3. *ADMIN GRANT:*
   Contact support for special access

🎁 *Current VIP Codes Available:*
`WELCOME2024` - 30 days free
`VIPACCESS` - 60 days free
`YOUTUBER` - 90 days free
`INFLUENCER` - 180 days free
`DEVIL` - 365 days free 👑

⚡ *Redeem Code:*
/vip [code]
Example: `/vip WELCOME2024`
"""
        
        keyboard = []
        if not is_premium:
            keyboard.append([InlineKeyboardButton("🎟️ Redeem VIP Code", callback_data="redeem_vip")])
        keyboard.append([InlineKeyboardButton("👥 Referral Program", callback_data="referral_info")])
        keyboard.append([InlineKeyboardButton("💬 Contact Support", url="https://t.me/your_support")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            premium_text,
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    
    async def myplan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's current plan"""
        user = update.effective_user
        user_data = db.get_user(user.id)
        is_premium = self.is_premium_user(user.id)
        
        daily_used = user_data.get('daily_downloads', 0)
        daily_limit = PremiumConfig.PREMIUM_DAILY_LIMIT if is_premium else PremiumConfig.FREE_DAILY_LIMIT
        total_downloads = user_data.get('total_downloads', 0)
        
        # Calculate progress bar
        progress = int((daily_used / daily_limit) * 10)
        progress_bar = "▓" * progress + "░" * (10 - progress)
        
        plan_text = f"""
📊 *YOUR ACCOUNT STATUS*

👤 User: {user.first_name}
🆔 ID: `{user.id}`
🎮 Status: {"👑 **VIP PREMIUM**" if is_premium else "🎯 **PRO USER**"}

📥 *Daily Usage:*
{progress_bar} {daily_used}/{daily_limit}
Reset: In {24 - datetime.now().hour} hours

📈 *Total Downloads:* {total_downloads}

⚡ *Your Limits:*
• Max quality: {PremiumConfig.PREMIUM_MAX_QUALITY if is_premium else PremiumConfig.FREE_MAX_QUALITY}
• Max size: {self.format_size(PremiumConfig.PREMIUM_MAX_SIZE if is_premium else PremiumConfig.FREE_MAX_SIZE)}
• Daily limit: {daily_limit} videos
"""
        
        if is_premium:
            premium_until = user_data.get('premium_until')
            if premium_until:
                try:
                    end_date = datetime.fromisoformat(premium_until)
                    days_left = (end_date - datetime.now()).days
                    plan_text += f"• Premium expires in: {days_left} days\n"
                except:
                    pass
        
        plan_text += f"""
🎁 *Referral Code:* `{user_data.get('referral_code', 'N/A')}`
👥 Referrals: {len(user_data.get('referrals', []))}

💡 *Tips:*
• Use /refer to invite friends
• Check /premium for VIP codes
• Contact support if needed
"""
        
        keyboard = []
        if not is_premium:
            keyboard.append([InlineKeyboardButton("👑 Get Premium", callback_data="premium_info")])
        keyboard.append([InlineKeyboardButton("👥 Refer Friends", callback_data="referral_info")])
        keyboard.append([InlineKeyboardButton("📥 Download Now", switch_inline_query_current_chat="")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            plan_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def download_video_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle download command"""
        if not context.args:
            await update.message.reply_text(
                "📥 *Usage:* `/download [video_url]`\n"
                "Example: `/download https://youtube.com/watch?v=...`",
                parse_mode='Markdown'
            )
            return
        
        url = context.args[0]
        await self.handle_video_url(update, url)
    
    async def handle_video_url(self, update: Update, url: str):
        """Process video URL"""
        user = update.effective_user
        
        # Check if user can download
        can_download, error_msg = self.can_download(user.id)
        if not can_download:
            await update.message.reply_text(error_msg)
            return
        
        # Check if URL is valid
        if not re.match(r'^https?://', url):
            await update.message.reply_text("❌ Please provide a valid URL starting with http:// or https://")
            return
        
        # Show processing message
        processing_msg = await update.message.reply_text(
            "🔍 *Analyzing video...*\n"
            "⏳ Please wait while I fetch video information...",
            parse_mode='Markdown'
        )
        
        try:
            # Get video info
            video_info = await self.downloader.get_video_info(url)
            
            if not video_info.get('success'):
                await processing_msg.edit_text(f"❌ Error: {video_info.get('error', 'Unknown error')}")
                return
            
            # Create quality selection keyboard
            keyboard = []
            formats = video_info.get('formats', [])
            
            # Sort formats by quality
            video_formats = [f for f in formats if f.get('height', 0) > 0]
            video_formats.sort(key=lambda x: x.get('height', 0), reverse=True)
            
            # Add best quality option
            keyboard.append([InlineKeyboardButton(
                "⚡ Best Quality (Auto)", 
                callback_data=f"download:{url}:best"
            )])
            
            # Add audio only option
            keyboard.append([InlineKeyboardButton(
                "🎵 Audio Only (MP3)", 
                callback_data=f"audio:{url}"
            )])
            
            # Add quality options (max 5)
            for fmt in video_formats[:5]:
                quality = fmt.get('quality', 'N/A')
                size = self.format_size(fmt.get('filesize', 0))
                text = f"🎬 {quality} ({size})"
                keyboard.append([InlineKeyboardButton(
                    text,
                    callback_data=f"download:{url}:{fmt['format_id']}"
                )])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Prepare info text
            info_text = f"""
📹 *Video Information:*

📌 *Title:* {video_info['title']}
👤 *Uploader:* {video_info['uploader']}
⏱️ *Duration:* {self.format_duration(video_info['duration'])}
👁️ *Views:* {video_info['view_count']:,}
👍 *Likes:* {video_info.get('like_count', 'N/A')}
🌐 *Source:* {video_info['extractor'].upper()}

👇 *Select download option:*
            """
            
            # Send with thumbnail if available
            if video_info.get('thumbnail'):
                try:
                    await update.message.reply_photo(
                        photo=video_info['thumbnail'],
                        caption=info_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    await processing_msg.delete()
                except:
                    await processing_msg.edit_text(
                        info_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
            else:
                await processing_msg.edit_text(
                    info_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            await processing_msg.edit_text(f"❌ Error: {str(e)}")
            logger.error(f"Video info error: {traceback.format_exc()}")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user = query.from_user
        
        if data.startswith("download:"):
            _, url, format_id = data.split(":", 2)
            await self.process_download(query, url, format_id)
        
        elif data.startswith("audio:"):
            url = data.split(":", 1)[1]
            await self.process_audio(query, url)
        
        elif data == "premium_info":
            await self.premium_info(update, context)
        
        elif data == "help_menu":
            await self.help_command(update, context)
        
        elif data == "referral_info":
            await self.referral_command(update, context)
        
        elif data == "redeem_vip":
            await query.message.reply_text(
                "🎟️ *Redeem VIP Code:*\n\n"
                "Use command: `/vip [code]`\n\n"
                "Available codes:\n"
                "`WELCOME2024` - 30 days free\n"
                "`VIPACCESS` - 60 days free\n"
                "`YOUTUBER` - 90 days free\n"
                "`INFLUENCER` - 180 days free\n"
                "`DEVIL` - 365 days free 👑",
                parse_mode='Markdown'
            )
    
    async def process_download(self, query, url: str, format_id: str):
        """Process video download"""
        user = query.from_user
        
        # Check download limit
        can_download, error_msg = self.can_download(user.id)
        if not can_download:
            await query.message.reply_text(error_msg)
            return
        
        status_msg = await query.message.reply_text(
            "⏬ *Downloading video...*\n"
            "⚡ This may take a moment...",
            parse_mode='Markdown'
        )
        
        try:
            success, filename, title = await self.downloader.download_video(url, format_id)
            
            if not success:
                await status_msg.edit_text(f"❌ Download failed: {filename}")
                return
            
            # Check file size
            file_size = os.path.getsize(filename)
            is_premium = self.is_premium_user(user.id)
            max_size = PremiumConfig.PREMIUM_MAX_SIZE if is_premium else PremiumConfig.FREE_MAX_SIZE
            
            if file_size > max_size:
                os.remove(filename)
                await status_msg.edit_text(
                    f"❌ File too large! ({self.format_size(file_size)})\n"
                    f"Limit: {self.format_size(max_size)}\n"
                    f"Upgrade to premium for larger files!"
                )
                return
            
            await status_msg.edit_text("📤 *Uploading to Telegram...*")
            
            # Send video
            with open(filename, 'rb') as video_file:
                await query.message.reply_video(
                    video=video_file,
                    caption=f"✅ *Download Complete!*\n\n"
                          f"📹 *{clean_filename(title)}*\n"
                          f"📦 Size: {self.format_size(file_size)}\n"
                          f"👤 User: {user.first_name}\n"
                          f"🎮 Status: {'👑 Premium' if is_premium else '🎯 Free'}",
                    parse_mode='Markdown',
                    supports_streaming=True
                )
            
            # Update download count
            self.update_download_count(user.id)
            
            await status_msg.delete()
            
            # Clean up
            try:
                os.remove(filename)
            except:
                pass
            
        except Exception as e:
            await status_msg.edit_text(f"❌ Error: {str(e)}")
            logger.error(f"Download error: {traceback.format_exc()}")
    
    async def process_audio(self, query, url: str):
        """Process audio download"""
        user = query.from_user
        
        # Check download limit
        can_download, error_msg = self.can_download(user.id)
        if not can_download:
            await query.message.reply_text(error_msg)
            return
        
        status_msg = await query.message.reply_text(
            "🎵 *Extracting audio...*\n"
            "⏳ Converting to MP3...",
            parse_mode='Markdown'
        )
        
        try:
            success, filename, title = await self.downloader.download_audio(url)
            
            if not success:
                await status_msg.edit_text(f"❌ Audio extraction failed: {filename}")
                return
            
            await status_msg.edit_text("📤 *Uploading audio...*")
            
            # Send audio
            with open(filename, 'rb') as audio_file:
                await query.message.reply_audio(
                    audio=audio_file,
                    caption=f"✅ *Audio Extracted!*\n\n"
                          f"🎵 *{clean_filename(title)}*\n"
                          f"👤 User: {user.first_name}\n"
                          f"🎮 Status: {'👑 Premium' if self.is_premium_user(user.id) else '🎯 Free'}",
                    parse_mode='Markdown'
                )
            
            # Update download count
            self.update_download_count(user.id)
            
            await status_msg.delete()
            
            # Clean up
            try:
                os.remove(filename)
            except:
                pass
            
        except Exception as e:
            await status_msg.edit_text(f"❌ Error: {str(e)}")
            logger.error(f"Audio error: {traceback.format_exc()}")
    
    async def audio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Audio extraction command"""
        if not context.args:
            await update.message.reply_text(
                "🎵 *Usage:* `/audio [video_url]`\n"
                "Example: `/audio https://youtube.com/watch?v=...`",
                parse_mode='Markdown'
            )
            return
        
        url = context.args[0]
        user = update.effective_user
        
        # Create mock query object
        class MockQuery:
            def __init__(self, message, user):
                self.message = message
                self.from_user = user
            
            async def answer(self):
                pass
        
        query = MockQuery(update.message, user)
        await self.process_audio(query, url)
    
    async def referral_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Referral program"""
        user = update.effective_user
        user_data = db.get_user(user.id)
        referral_code = user_data.get('referral_code', 'N/A')
        
        referral_text = f"""
👥 *REFERRAL PROGRAM*

🎁 *Earn {PremiumConfig.REFERRAL_BONUS} extra downloads per referral!*

📋 *How it works:*
1. Share your referral link
2. Friend joins using your link
3. You get {PremiumConfig.REFERRAL_BONUS} bonus downloads
4. Friend gets {PremiumConfig.REFERRAL_BONUS} bonus downloads

🔗 *Your Referral Link:*
`https://t.me/{context.bot.username}?start={referral_code}`

📝 *Your Referral Code:* `{referral_code}`

📊 *Your Stats:*
• Total Referrals: {len(user_data.get('referrals', []))}
• Bonus Downloads: {len(user_data.get('referrals', [])) * PremiumConfig.REFERRAL_BONUS}

⚡ *Quick Share:*
"""
        
        keyboard = [
            [
                InlineKeyboardButton("📱 Share Link", 
                    url=f"https://t.me/share/url?url=https://t.me/{context.bot.username}?start={referral_code}&text=Join%20this%20awesome%20video%20downloader%20bot!")
            ],
            [
                InlineKeyboardButton("📋 Copy Code", 
                    callback_data=f"copy:{referral_code}")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            referral_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def vip_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Redeem VIP code"""
        if not context.args:
            await update.message.reply_text(
                "🎟️ *Usage:* `/vip [code]`\n\n"
                "Available VIP codes:\n"
                "`WELCOME2024` - 30 days\n"
                "`VIPACCESS` - 60 days\n"
                "`YOUTUBER` - 90 days\n"
                "`INFLUENCER` - 180 days\n"
                "`DEVIL` - 365 days 👑",
                parse_mode='Markdown'
            )
            return
        
        code = context.args[0].upper()
        user = update.effective_user
        
        # Check if code exists
        if code not in PremiumConfig.VIP_CODES:
            await update.message.reply_text(
                f"❌ Invalid VIP code: `{code}`\n\n"
                "Available codes:\n"
                "`WELCOME2024`, `VIPACCESS`, `YOUTUBER`, `INFLUENCER`, `DEVIL`",
                parse_mode='Markdown'
            )
            return
        
        user_data = db.get_user(user.id)
        redeemed = user_data.get('redeemed_codes', [])
        
        # Check if already redeemed
        if code in redeemed:
            await update.message.reply_text(f"❌ Code `{code}` already redeemed!")
            return
        
        # Add premium days
        days = PremiumConfig.VIP_CODES[code]
        premium_until = datetime.now() + timedelta(days=days)
        
        # Update user
        redeemed.append(code)
        db.update_user(user.id, {
            'is_premium': True,
            'premium_until': premium_until.isoformat(),
            'redeemed_codes': redeemed
        })
        
        await update.message.reply_text(
            f"🎉 *VIP CODE REDEEMED!* 🎉\n\n"
            f"Code: `{code}`\n"
            f"Days added: {days}\n"
            f"Premium until: {premium_until.strftime('%Y-%m-%d')}\n\n"
            f"✨ *Welcome to VIP PREMIUM!* ✨\n"
            f"You now have access to all premium features!",
            parse_mode='Markdown'
        )
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """User statistics"""
        user = update.effective_user
        user_data = db.get_user(user.id)
        
        daily_used = user_data.get('daily_downloads', 0)
        total_downloads = user_data.get('total_downloads', 0)
        referrals = len(user_data.get('referrals', []))
        
        # Calculate progress
        is_premium = self.is_premium_user(user.id)
        daily_limit = PremiumConfig.PREMIUM_DAILY_LIMIT if is_premium else PremiumConfig.FREE_DAILY_LIMIT
        progress = min(100, int((daily_used / daily_limit) * 100))
        
        stats_text = f"""
📊 *YOUR STATISTICS*

👤 User: {user.first_name}
🎮 Status: {"👑 VIP PREMIUM" if is_premium else "🎯 PRO USER"}

📥 *Downloads Today:*
{daily_used}/{daily_limit} ({progress}%)
{get_progress_bar(progress)}

📈 *Total Downloads:* {total_downloads:,}

👥 *Referrals:* {referrals}
🎁 *Bonus Downloads:* {referrals * PremiumConfig.REFERRAL_BONUS}

⚡ *Next Reset:* In {24 - datetime.now().hour} hours

💡 *Tips:*
• Invite friends for bonus downloads
• Check /premium for VIP codes
• Use /batch for multiple videos
"""
        
        await update.message.reply_text(
            stats_text,
            parse_mode='Markdown'
        )
    
    async def trending_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show trending videos"""
        trending_text = """
🔥 *TRENDING NOW*

🎬 *YouTube Trending:*
1. [Video Title 1](https://youtube.com)
2. [Video Title 2](https://youtube.com)
3. [Video Title 3](https://youtube.com)

💃 *TikTok Trending:*
1. [Trending Video 1](https://tiktok.com)
2. [Trending Video 2](https://tiktok.com)

📸 *Instagram Reels:*
1. [Reel 1](https://instagram.com)
2. [Reel 2](https://instagram.com)

⚡ *How to download:*
Just send the video URL to me!

💡 *Pro Tip:* Use /search to find specific videos
"""
        
        await update.message.reply_text(
            trending_text,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    
    # ======================
    # ADMIN COMMANDS
    # ======================
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin panel"""
        user = update.effective_user
        
        if user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Admin only command!")
            return
        
        admin_text = """
🛠️ *ADMIN PANEL*

📊 *Statistics:*
/users - View all users
/statsall - Complete statistics
/broadcast - Send message to all

👑 *Premium Management:*
/addpremium [id] - Add premium user
/removepremium [id] - Remove premium
/setlimit [id] [num] - Set download limit

⚙️ *Bot Management:*
/backup - Backup database
/restart - Restart bot
/logs - View logs

📈 *Quick Stats:*
"""
        
        # Get quick stats
        try:
            with open("users.json", 'r') as f:
                users = json.load(f)
            
            total_users = len(users)
            premium_users = sum(1 for u in users.values() if u.get('is_premium'))
            
            with open("downloads.json", 'r') as f:
                downloads = json.load(f)
            
            total_downloads = len(downloads)
            
            admin_text += f"""
• Total Users: {total_users}
• Premium Users: {premium_users}
• Total Downloads: {total_downloads}
"""
        
        except:
            admin_text += "• Stats: Error loading"
        
        await update.message.reply_text(
            admin_text,
            parse_mode='Markdown'
        )
    
    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast message to all users"""
        user = update.effective_user
        
        if user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Admin only command!")
            return
        
        if not context.args:
            await update.message.reply_text("Usage: /broadcast [message]")
            return
        
        message = " ".join(context.args)
        broadcast_text = f"""
📢 *ANNOUNCEMENT FROM ADMIN*

{message}

---
*This is a broadcast message to all users.*
"""
        
        try:
            with open("users.json", 'r') as f:
                users = json.load(f)
            
            sent = 0
            failed = 0
            
            for user_id in users.keys():
                try:
                    await context.bot.send_message(
                        chat_id=int(user_id),
                        text=broadcast_text,
                        parse_mode='Markdown'
                    )
                    sent += 1
                except:
                    failed += 1
                await asyncio.sleep(0.1)  # Rate limiting
            
            await update.message.reply_text(
                f"📤 Broadcast completed!\n"
                f"✅ Sent: {sent}\n"
                f"❌ Failed: {failed}"
            )
        
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

# ======================
# HELPER FUNCTIONS
# ======================
def clean_filename(filename: str) -> str:
    """Clean filename"""
    import re
    cleaned = re.sub(r'[<>:"/\\|?*]', '', filename)
    if len(cleaned) > 100:
        cleaned = cleaned[:100]
    return cleaned

def get_progress_bar(percentage: int, length: int = 10) -> str:
    """Get progress bar string"""
    filled = int(length * percentage / 100)
    return "█" * filled + "░" * (length - filled)

# ======================
# BOT SETUP
# ======================
async def post_init(application: Application):
    """Set bot commands after initialization"""
    await application.bot.set_my_commands([
        BotCommand("start", "🚀 Start the bot"),
        BotCommand("help", "📚 Show all commands"),
        BotCommand("download", "⬇️ Download video"),
        BotCommand("premium", "👑 Premium features"),
        BotCommand("myplan", "📊 Your current plan"),
        BotCommand("audio", "🎵 Extract audio"),
        BotCommand("stats", "📈 Your statistics"),
        BotCommand("refer", "👥 Refer & earn"),
        BotCommand("vip", "🎟️ Redeem VIP code"),
    ])

def main():
    """Start the bot"""
    # Check token
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ ERROR: BOT_TOKEN not set!")
        print("Set BOT_TOKEN in environment variables or .env file")
        return
    
    print(f"""
╔══════════════════════════════════╗
║     PREMIUM VIDEO DOWNLOADER     ║
║            🤖 BOT               ║
╚══════════════════════════════════╝
    
✅ Token: {BOT_TOKEN[:15]}...
✅ Admin IDs: {ADMIN_IDS}
✅ Starting bot...
    """)
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Initialize bot
    bot = CoolVideoBot()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("premium", bot.premium_info))
    application.add_handler(CommandHandler("myplan", bot.myplan))
    application.add_handler(CommandHandler("download", bot.download_video_command))
    application.add_handler(CommandHandler("audio", bot.audio_command))
    application.add_handler(CommandHandler("refer", bot.referral_command))
    application.add_handler(CommandHandler("vip", bot.vip_command))
    application.add_handler(CommandHandler("stats", bot.stats_command))
    application.add_handler(CommandHandler("trending", bot.trending_command))
    application.add_handler(CommandHandler("admin", bot.admin_command))
    application.add_handler(CommandHandler("broadcast", bot.broadcast_command))
    
    # Add platform-specific commands
    platform_commands = ["ytdl", "tiktok", "insta", "twitter", "facebook"]
    for cmd in platform_commands:
        application.add_handler(CommandHandler(cmd, bot.download_video_command))
    
    # Add message handler for URLs
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        lambda update, context: bot.handle_video_url(update, update.message.text)
    ))
    
    # Add callback handler
    application.add_handler(CallbackQueryHandler(bot.button_callback))
    
    # Reset daily counts periodically
    async def reset_counts(context: ContextTypes.DEFAULT_TYPE):
        db.reset_daily_counts()
    
    # Start bot
    print("🤖 Bot is running...")
    print("📱 Go to Telegram and start using!")
    
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"]
    )

if __name__ == '__main__':
    main()
