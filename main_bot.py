import os
import time
import threading
import telebot
from dotenv import load_dotenv
from oci_manager import OciManager

load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_API_KEY')
USER_ID = os.getenv('TELEGRAM_USER_ID')

if not BOT_TOKEN or not USER_ID:
    print("Error: TELEGRAM_BOT_API_KEY and TELEGRAM_USER_ID must be set in .env")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)
oci_manager = OciManager()

# Global state for the background task
running = False
background_thread = None

def check_capacity_loop():
    global running
    
    ads = []
    if oci_manager.ad_config:
        # User defined ADs
        import ast
        try:
            # Check if it looks like a list
            if oci_manager.ad_config.startswith('['):
                ads = ast.literal_eval(oci_manager.ad_config)
            else:
                ads = [oci_manager.ad_config]
        except:
            ads = [oci_manager.ad_config]
    else:
        ads = oci_manager.get_availability_domains()
        
    if not ads:
        bot.send_message(USER_ID, "❌ Failed to retrieve Availability Domains. Stopping.")
        running = False
        return

    bot.send_message(USER_ID, f"🚀 Started capacity checker loop. Target ADs: {', '.join(ads)}")
    
    while running:
        max_reached, count = oci_manager.check_existing_instances()
        if max_reached:
            bot.send_message(USER_ID, f"✅ Max instances ({count}/{oci_manager.max_instances}) already reached. Stopping loop.")
            running = False
            break
            
        success = False
        for ad in ads:
            if not running:
                break
                
            bot.send_message(USER_ID, f"⏳ Attempting to launch in {ad}...")
            
            created, response_or_error = oci_manager.launch_instance(ad)
            if created:
                bot.send_message(USER_ID, f"🎉 SUCCESS! Instance launched in {ad}.\n\nDetails:\n{response_or_error}")
                success = True
                running = False
                break
            else:
                if "Out of host capacity" in response_or_error:
                    # Don't spam the user on every capacity error, just log internally or maybe send a silent update occasionally
                    print(f"Capacity error in {ad}: {response_or_error}")
                else:
                    bot.send_message(USER_ID, f"⚠️ Error in {ad}:\n{response_or_error}")
                    
        if not success and running:
            # Wait 60 seconds before trying again to avoid rate limiting
            time.sleep(60)

def require_auth(func):
    def wrapper(message, *args, **kwargs):
        if str(message.from_user.id) != str(USER_ID):
            bot.reply_to(message, "Unauthorized user.")
            return
        return func(message, *args, **kwargs)
    return wrapper

@bot.message_handler(commands=['start', 'help'])
@require_auth
def send_welcome(message):
    help_text = (
        "🤖 *OCI ARM Host Capacity Bot*\n\n"
        "Commands:\n"
        "/status - Check OCI instances and connection status\n"
        "/run - Start the background capacity checker\n"
        "/stop - Stop the background capacity checker\n"
    )
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['status'])
@require_auth
def check_status(message):
    bot.reply_to(message, "🔍 Checking OCI status...")
    if not oci_manager.compute_client:
        bot.send_message(message.chat.id, "❌ OCI Client not initialized. Check your .env file and credentials.")
        return
        
    max_reached, count = oci_manager.check_existing_instances()
    if count == -1:
        bot.send_message(message.chat.id, "❌ Failed to fetch instances. Check logs.")
    else:
        status_msg = f"✅ Connection successful.\n"
        status_msg += f"Running instances: {count}/{oci_manager.max_instances}\n"
        status_msg += f"Background loop running: {'Yes 🏃' if running else 'No 🛑'}"
        bot.send_message(message.chat.id, status_msg)

@bot.message_handler(commands=['run'])
@require_auth
def start_loop(message):
    global running, background_thread
    if running:
        bot.reply_to(message, "⚠️ The capacity checker is already running!")
        return
        
    running = True
    background_thread = threading.Thread(target=check_capacity_loop)
    background_thread.start()
    bot.reply_to(message, "✅ Initializing background capacity checker...")

@bot.message_handler(commands=['stop'])
@require_auth
def stop_loop(message):
    global running
    if not running:
        bot.reply_to(message, "⚠️ The capacity checker is not currently running.")
        return
        
    running = False
    bot.reply_to(message, "🛑 Stopping the background capacity checker... It will stop after the current attempt finishes.")

if __name__ == "__main__":
    print("Bot is starting...")
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"Fatal error: {e}")
