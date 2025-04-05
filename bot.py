import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from image_processor import processImg  
from plcBridge import makeDraw
from dotenv import load_dotenv
import os

# Load variables from .env into the environment
load_dotenv()

# Access the variables
TOKEN_TELEGRAM = os.getenv('TOKEN_TELEGRAM')

# Define states
ASK_TO_DRAW, RECEIVE_IMAGE, PROCESS_IMAGE = range(3)
points = []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Do you want to draw something? (yes/no)")
    return ASK_TO_DRAW

async def ask_to_draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_response = update.message.text.lower()
    if user_response == "yes":
        await update.message.reply_text("Please send an image.")
        return RECEIVE_IMAGE
    else:
        await update.message.reply_text("Okay, maybe next time!")
        return ConversationHandler.END

async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        await photo_file.download_to_drive('input.png')
        await update.message.reply_text("Image received. Processing...")

        global points

        points = await processImg('input.png')

        # Assuming 'contour.png' is generated after processing
        if os.path.exists('contour.png'):
            await update.message.reply_photo(photo=open('sketch.png', 'rb'))
            await update.message.reply_text(f"Do you want to draw this result? It will take {len(points)} movements. (yes/no)")

            return PROCESS_IMAGE
        else:
            await update.message.reply_text("Error: Output image not found.")
            return ConversationHandler.END
    else:
        await update.message.reply_text("Please send a valid image.")
        return RECEIVE_IMAGE

async def process_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_response = update.message.text.lower()
    if user_response == "yes":
       
        await update.message.reply_text("Drawing the result...")

        global points 

        await makeDraw(points)

        await update.message.reply_text("Finished!!")

    else:
        await update.message.reply_text("Okay, stopping the process.")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Process cancelled.")
    return ConversationHandler.END

def main():
    global TOKEN_TELEGRAM
    
    application = Application.builder().token(TOKEN_TELEGRAM).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_TO_DRAW: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_to_draw)],
            RECEIVE_IMAGE: [MessageHandler(filters.PHOTO, receive_image)],
            PROCESS_IMAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_image)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":
    main()