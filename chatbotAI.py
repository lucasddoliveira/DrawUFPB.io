import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from dotenv import load_dotenv
import requests
from groq import Groq
from io import BytesIO
from image_processor import processImg  # Import from bot.py
from plcBridge import makeDraw  # Import from bot.py
from huggingface_hub import InferenceClient

# Load environment variables
load_dotenv()

# Access API tokens
TOKEN_TELEGRAM = os.getenv('TOKEN_TELEGRAM')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
HUGGINGFACE_API_KEY= os.getenv('HUGGINGFACE_API_KEY')
# Initialize Groq client
groq_client = Groq(api_key=GROQ_API_KEY)

# Define conversation states
CHATTING, GENERATING_IMAGE, DRAWING_CONFIRM, UPLOAD_PHOTO = range(4)

# Store conversation history for each user
user_conversations = {}
# Store points for drawing
points = []
# Store generated image path for current session
current_image_path = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the conversation and initialize user context."""
    user_id = update.effective_user.id
    user_conversations[user_id] = [{
            "role": "system",
            "content": """You are a friendly and knowledgeable assistant designed to help users create drawings using a robotic arm. Your mission is to guide them step-by-step—from generating creative images to transforming them into real-world sketches using the robot. 🎨 How to Interact with Me: Just send a message to start a conversation. Want to turn your imagination into art? Use the /image command followed by a description. Example: /image a cat wearing sunglasses. After generating your image, I'll ask if you'd like to draw it with the robotic arm. 📚 Available Commands: /start – Start or restart the conversation. /image – Generate an image from a description. /help – Show this help message. /clear – Clear the conversation history. /cancel – Cancel the current operation. /upload - Upload your own photo for drawing. Let's make something amazing together! 🤖🖋️"""
        }]
 
    welcome_message = (
        "👋 Hello! I'm an AI assistant that can help you make drawings with the robotic arm!\n\n"
        "I can:\n"
        "• Chat with you using Groq's LLM\n"
        "• Generate images based on your descriptions\n"
        "• Process your uploaded photos\n"
        "• Draw images using a robotic arm\n\n"
        "Commands:\n"
        "/start - Start/restart the conversation\n"
        "/image - Generate an image\n"
        "/upload - Upload your own photo\n"
        "/help - Show this help message\n"
        "/clear - Clear your conversation history\n"
        "/cancel - Cancel current operation"
    )
    
    await update.message.reply_text(welcome_message)
    return CHATTING

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display help information."""
    help_message = (
        "📚 Available commands:\n\n"
        "/start - Start/restart the conversation\n"
        "/image - Generate an image\n"
        "/upload - Upload your own photo\n"
        "/help - Show this help message\n"
        "/clear - Clear your conversation history\n"
        "/cancel - Cancel current operation\n\n"
        "Just send a message to chat with me, use /image to generate an image, "
        "or use /upload to draw your own photos with the robotic arm."
    )
    
    await update.message.reply_text(help_message)
    return CHATTING

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear the conversation history for the user."""
    user_id = update.effective_user.id
    user_conversations[user_id] = [{
            "role": "system",
            "content": """You are a friendly and knowledgeable assistant designed to help users create drawings using a robotic arm. Your mission is to guide them step-by-step—from generating creative images to transforming them into real-world sketches using the robot. 🎨 How to Interact with Me: Just send a message to start a conversation. Want to turn your imagination into art? Use the /image command followed by a description. Example: /image a cat wearing sunglasses. After generating your image, I'll ask if you'd like to draw it with the robotic arm. 📚 Available Commands: /start – Start or restart the conversation. /image – Generate an image from a description. /help – Show this help message. /clear – Clear the conversation history. /cancel – Cancel the current operation. /upload - Upload your own photo for drawing. Let's make something amazing together! 🤖🖋️"""
        }]
    
    await update.message.reply_text("Conversation history cleared! Let's start fresh.")
    return CHATTING

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages and generate AI responses."""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Initialize user conversation history if not exists
    if user_id not in user_conversations:
        user_conversations[user_id] = [{
            "role": "system",
            "content": """You are a friendly and knowledgeable assistant designed to help users create drawings using a robotic arm. Your mission is to guide them step-by-step—from generating creative images to transforming them into real-world sketches using the robot. 🎨 How to Interact with Me: Just send a message to start a conversation. Want to turn your imagination into art? Use the /image command followed by a description. Example: /image a cat wearing sunglasses. After generating your image, I'll ask if you'd like to draw it with the robotic arm. 📚 Available Commands: /start – Start or restart the conversation. /image – Generate an image from a description. /help – Show this help message. /clear – Clear the conversation history. /cancel – Cancel the current operation. /upload - Upload your own photo for drawing. Let's make something amazing together! 🤖🖋️"""
        }]
    
    # Add user message to history
    user_conversations[user_id].append({"role": "user", "content": user_message}) 
    
    # Show typing indicator
    await update.message.chat.send_action(action="typing")
    
    try:
        # Get AI response from Groq
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=user_conversations[user_id],
            max_tokens=1024,
            temperature=0.7,
            top_p=0.9
        )
        
        assistant_message = response.choices[0].message.content
        
        # Add assistant response to history
        user_conversations[user_id].append({"role": "assistant", "content": assistant_message})
        
        # Send response to user
        await update.message.reply_text(assistant_message)
        
    except Exception as e:
        await update.message.reply_text(f"Sorry, I encountered an error: {str(e)}")
        
    return CHATTING

async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start image generation process."""
    await update.message.reply_text("Please describe the image you want me to generate:")
    return GENERATING_IMAGE


async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate an image based on user prompt using Hugging Face FLUX.1-dev model."""
    global current_image_path
    global points

    prompt = update.message.text

    await update.message.reply_text(f"Generating image for: '{prompt}'... This might take a moment.")
    await update.message.chat.send_action(action="upload_photo")

    try:
        # Using Hugging Face FLUX.1-dev model
        API_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-dev"
        headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}

        payload = {
            "inputs": prompt,
        }

        # Make request to Hugging Face API
        response = requests.post(API_URL, headers=headers, json=payload)

        if response.status_code == 200:
            # Ensure steps directory exists
            os.makedirs('steps', exist_ok=True)

            # Save the image to file
            current_image_path = 'steps/input.png'
            with open(current_image_path, 'wb') as f:
                f.write(response.content)

            # Send the image
            await update.message.reply_photo(photo=open(current_image_path, 'rb'))
            await update.message.reply_text(f"Processing this result...This is usually fast.")
            # Process image for drawing
            points = await processImg(current_image_path)

            # Send processed image preview
            if os.path.exists('steps/sketch.png'):
                await update.message.reply_photo(photo=open('steps/contour.png', 'rb'))
                await update.message.reply_photo(photo=open('steps/sketch.png', 'rb'))
                await update.message.reply_text(
                    f"Here's your generated image and how it would look when drawn! "
                    f"Would you like to draw this with the robotic arm? It will take {len(points)} movements. (yes/no)"
                )
                return DRAWING_CONFIRM
            else:
                await update.message.reply_text(
                    "Image generated successfully, but I couldn't create a drawing preview. "
                    "Would you like to try drawing it anyway? (yes/no)"
                )
                return DRAWING_CONFIRM

        else:
            error_message = f"API Error: {response.status_code}"
            try:
                error_data = response.json()
                if "error" in error_data:
                    error_message = f"Image generation failed: {error_data['error']}"
            except:
                pass

            await update.message.reply_text(error_message)
            return CHATTING

    except Exception as e:
        await update.message.reply_text(f"Sorry, I encountered an error generating the image: {str(e)}")
        return CHATTING
    

async def upload_photo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start photo upload process."""
    await update.message.reply_text(
        "Please upload the photo you want to draw with the robotic arm.\n\n"
        "For best results, upload images with clear outlines and good contrast."
    )
    return UPLOAD_PHOTO

async def process_uploaded_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process a photo uploaded by the user."""
    global current_image_path
    global points
    
    # Ensure the message contains a photo
    if not update.message.photo:
        await update.message.reply_text("No photo detected. Please upload a photo or use /cancel to return.")
        return UPLOAD_PHOTO
    
    # Get the largest photo (best quality)
    photo = update.message.photo[-1]
    
    await update.message.reply_text("Processing your photo... Please wait.")
    await update.message.chat.send_action(action="typing")
    
    try:
        # Get the file from Telegram
        file = await context.bot.get_file(photo.file_id)
        
        # Ensure steps directory exists
        os.makedirs('steps', exist_ok=True)
        
        # Set the file path
        current_image_path = 'steps/input.png'
        
        # Download the file
        await file.download_to_drive(current_image_path)
        
        # Process image for drawing
        points = await processImg(current_image_path)
        
        # Send processed image preview
        if os.path.exists('steps/sketch.png'):
            await update.message.reply_photo(photo=open('steps/contour.png', 'rb'))
            await update.message.reply_photo(photo=open('steps/sketch.png', 'rb'))
            await update.message.reply_text(
                f"Here's how your photo would look when drawn! "
                f"Would you like to draw this with the robotic arm? It will take {len(points)} movements. (yes/no)"
            )
        else:
            await update.message.reply_text(
                "Photo processed, but I couldn't create a drawing preview. "
                "Would you like to try drawing it anyway? (yes/no)"
            )
        
        return DRAWING_CONFIRM
        
    except Exception as e:
        await update.message.reply_text(f"Sorry, I encountered an error processing your photo: {str(e)}")
        return CHATTING

async def draw_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmation for drawing the generated image."""
    global points
    
    user_response = update.message.text.lower()
    
    if user_response == "yes":
        await update.message.reply_text("Starting the drawing process... I'll be back when the drawing is done!")
        
        try:
            # Draw using the robotic arm
            await makeDraw(points)
            await update.message.reply_text("Drawing completed successfully! What would you like to do next?")
        except Exception as e:
            await update.message.reply_text(f"Sorry, I encountered an error while drawing: {str(e)}")
    else:
        await update.message.reply_text("No problem! The image won't be drawn. What would you like to do next?")
    
    return CHATTING

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the current operation."""
    await update.message.reply_text("Current operation cancelled. What would you like to do?")
    return CHATTING

def main():
    """Run the bot."""
    # Create the Application
    application = Application.builder().token(TOKEN_TELEGRAM).build()

    # Set up the ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHATTING: [
                CommandHandler("help", help_command),
                CommandHandler("image", image_command),
                CommandHandler("upload", upload_photo_command),
                CommandHandler("clear", clear_history),
                MessageHandler(filters.TEXT & ~filters.COMMAND, chat),
            ],
            GENERATING_IMAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, generate_image),
            ],
            UPLOAD_PHOTO: [
                MessageHandler(filters.PHOTO, process_uploaded_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda update, context: 
                    update.message.reply_text("Please upload a photo or use /cancel to go back.")),
            ],
            DRAWING_CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, draw_confirm),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    
    # Start the Bot
    print("Starting bot...")
    application.run_polling()

if __name__ == "__main__":
    main()