import logging
import asyncio
import nest_asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from imagehash import phash, ImageHash
from PIL import Image
import io

# Apply nest_asyncio to avoid "event loop already running" issues
nest_asyncio.apply()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Token (Replace with your actual token)
TOKEN = "8163988856:AAHVqvHv2Vw_D2v1NLVfCPPGhk4d2cy7ruI"

# Dictionary to store perceptual hashes per chat {chat_id: [(message_id, hash)]}
chat_phash_dict = {}

# Hamming distance threshold
THRESHOLD = 10  # Adjust if needed

def find_duplicate(chat_id, new_hash: ImageHash):
    """Check if an image is a duplicate within the same chat."""
    if chat_id not in chat_phash_dict:
        return None, None  

    for msg_id, existing_hash in chat_phash_dict[chat_id]:
        distance = new_hash - existing_hash  
        logger.info(f"Comparing hashes in chat {chat_id}: Distance = {distance}")
        if distance <= THRESHOLD:
            return msg_id, existing_hash  
    return None, None

async def photo_handler(update: Update, context: CallbackContext):
    """Handles photos and checks for duplicates."""
    try:
        message = update.effective_message
        if not message or not message.photo:
            return  

        chat_id = message.chat_id
        message_id = message.message_id
        photo = message.photo[-1]
        file = await context.bot.get_file(photo.file_id)

        bio = io.BytesIO()
        await file.download_to_memory(bio)
        bio.seek(0)

        image = Image.open(bio)
        image_hash = phash(image)  

        logger.info(f"Computed hash for chat {chat_id}: {image_hash}")

        duplicate_msg_id, duplicate_hash = find_duplicate(chat_id, image_hash)

        if duplicate_msg_id:
            keyboard = [
                [
                    InlineKeyboardButton("Yes, they are duplicates", callback_data=f"confirm_duplicate:{duplicate_msg_id}:{message_id}"),
                    InlineKeyboardButton("No, they are different", callback_data="not_duplicate")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=chat_id,
                text="The bot detected similar images.\nDo you confirm that they are duplicates?",
                reply_markup=reply_markup,
                reply_to_message_id=duplicate_msg_id
            )
        else:
            if chat_id not in chat_phash_dict:
                chat_phash_dict[chat_id] = []
            chat_phash_dict[chat_id].append((message_id, image_hash))
            logger.info(f"✅ New image stored in chat {chat_id}. Total stored: {len(chat_phash_dict[chat_id])}")

    except Exception as e:
        logger.error(f"Error in photo_handler: {e}")

async def confirmation_handler(update: Update, context: CallbackContext):
    """Handles user's response to duplicate confirmation."""
    query = update.callback_query
    await query.answer()

    try:
        if query.data == "not_duplicate":
            await query.edit_message_text("✅ Images are not duplicates. No action taken.")
            return  

        _, msg1, msg2 = query.data.split(":")
        msg1, msg2 = int(msg1), int(msg2)

        keyboard = [
            [
                InlineKeyboardButton("Delete pic1 (Earlier image)", callback_data=f"delete:{msg1}"),
                InlineKeyboardButton("Delete pic2 (New image)", callback_data=f"delete:{msg2}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text("Which image should be deleted?", reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error in confirmation_handler: {e}")

async def button_handler(update: Update, context: CallbackContext):
    """Handles image deletion."""
    query = update.callback_query
    await query.answer()

    try:
        _, msg_id = query.data.split(":")
        msg_id = int(msg_id)
        chat_id = query.message.chat_id

        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        await query.edit_message_text("✅ Image deleted successfully.")

        if chat_id in chat_phash_dict:
            chat_phash_dict[chat_id] = [(mid, h) for mid, h in chat_phash_dict[chat_id] if mid != msg_id]

    except Exception as e:
        logger.error(f"Error in button_handler: {e}")

async def main():
    """Starts the bot."""
    application = Application.builder().token(TOKEN).build()

    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    application.add_handler(CallbackQueryHandler(confirmation_handler, pattern=r"confirm_duplicate:|not_duplicate"))
    application.add_handler(CallbackQueryHandler(button_handler, pattern=r"delete:"))

    logger.info("🤖 Bot is running...")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())