import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from dotenv import load_dotenv
import requests
from groq import Groq
from io import BytesIO
from AmericoDraws import independencia_ou_morte
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
CHATTING, GENERATING_IMAGE, DRAWING_CONFIRM, UPLOAD_PHOTO, EDITING_PARAMS, WAITING_PARAM_VALUE = range(6)

# Store conversation history for each user
user_conversations = {}
# Store points for drawing
points = []
# Store generated image path for current session
current_image_path = None
# Store user-specific parameters
user_params = {}

# Default parameters for drawing
DEFAULT_PARAMS = {
    'process_cell_size': 1,
    'points_cell_width': 1,
    'z_up': -10,
    'remove_background': False,  # New parameter
    'bg_threshold': 10,
    'bg_erode_pixels': 1,
    'threshold1': 50,
    'threshold2': 191,
    'blur_size': 3,
    'distance_threshold': 3,
    'epsilon': 1,
    'linewidth': 5
}

# Add to EDITABLE_PARAMS list
EDITABLE_PARAMS = [
    ('process_cell_size', 'Resolution of image processing (lower = higher detail)'),
    ('points_cell_width', 'Width of each cell in points'),
    ('z_up', 'Height the pen moves up between strokes'),
    ('remove_background', 'Remove image background (1=yes, 0=no)'),  # New parameter
    ('bg_threshold', 'Background removal threshold'),
    ('bg_erode_pixels', 'Background erosion strength'),
    ('threshold1', 'Edge detection lower threshold'),
    ('threshold2', 'Edge detection upper threshold'),
    ('blur_size', 'Blur size for edge detection'),
    ('distance_threshold', 'Min distance between points'),
    ('epsilon', 'Simplification factor for lines'),
    ('linewidth', 'Width of drawn lines')
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the conversation and initialize user context."""
    user_id = update.effective_user.id
    user_conversations[user_id] = [{
            "role": "system",
            "content": """You are a friendly and knowledgeable assistant designed to help users create drawings using a robotic arm. Your mission is to guide them step-by-step—from generating creative images to transforming them into real-world sketches using the robot. 🎨 How to Interact with Me: Just send a message to start a conversation. Want to turn your imagination into art? Use the /image command followed by a description. Example: /image a cat wearing sunglasses. After generating your image, I'll ask if you'd like to draw it with the robotic arm. 📚 Available Commands: /start – Start or restart the conversation. /image – Generate an image from a description. /help – Show this help message. /clear – Clear the conversation history. /cancel – Cancel the current operation. /upload - Upload your own photo for drawing. /params - View and edit drawing parameters. Let's make something amazing together! 🤖🖋️"""
        }]
    
    # Initialize user parameters
    if user_id not in user_params:
        user_params[user_id] = DEFAULT_PARAMS.copy()
 
    welcome_message = (
        "👋 Hello! I'm an AI assistant that can help you make drawings with the robotic arm!\n\n"
        "I can:\n"
        "• Chat with you using Groq's LLM\n"
        "• Generate images based on your descriptions\n"
        "• Process your uploaded photos\n"
        "• Draw images using a robotic arm\n"
        "• Let you customize drawing parameters\n\n"
        "Commands:\n"
        "/start - Start/restart the conversation\n"
        "/image - Generate an image\n"
        "/upload - Upload your own photo\n"
        "/params - View and edit drawing parameters\n"
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
        "/params - View and edit drawing parameters\n"
        "/help - Show this help message\n"
        "/clear - Clear your conversation history\n"
        "/cancel - Cancel current operation\n\n"
        "Just send a message to chat with me, use /image to generate an image, "
        "use /upload to draw your own photos, or /params to customize the drawing process."
    )
    
    await update.message.reply_text(help_message)
    return CHATTING

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear the conversation history for the user."""
    user_id = update.effective_user.id
    user_conversations[user_id] = [{
            "role": "system",
            "content": """You are a friendly and knowledgeable assistant designed to help users create drawings using a robotic arm. Your mission is to guide them step-by-step—from generating creative images to transforming them into real-world sketches using the robot. 🎨 How to Interact with Me: Just send a message to start a conversation. Want to turn your imagination into art? Use the /image command followed by a description. Example: /image a cat wearing sunglasses. After generating your image, I'll ask if you'd like to draw it with the robotic arm. 📚 Available Commands: /start – Start or restart the conversation. /image – Generate an image from a description. /help – Show this help message. /clear – Clear the conversation history. /cancel – Cancel the current operation. /upload - Upload your own photo for drawing. /params - View and edit drawing parameters. Let's make something amazing together! 🤖🖋️"""
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
            "content": """You are a friendly and knowledgeable assistant designed to help users create drawings using a robotic arm. Your mission is to guide them step-by-step—from generating creative images to transforming them into real-world sketches using the robot. 🎨 How to Interact with Me: Just send a message to start a conversation. Want to turn your imagination into art? Use the /image command followed by a description. Example: /image a cat wearing sunglasses. After generating your image, I'll ask if you'd like to draw it with the robotic arm. 📚 Available Commands: /start – Start or restart the conversation. /image – Generate an image from a description. /help – Show this help message. /clear – Clear the conversation history. /cancel – Cancel the current operation. /upload - Upload your own photo for drawing. /params - View and edit drawing parameters. Let's make something amazing together! 🤖🖋️"""
        }]
    
    # Add user message to history
    user_conversations[user_id].append({"role": "user", "content": user_message}) 
    
    # Show typing indicator
    await update.message.chat.send_action(action="typing")
    
    try:
        # Geet AI response from Groq
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
    
    user_id = update.effective_user.id
    prompt = update.message.text
    
    # Make sure user parameters are initialized
    if user_id not in user_params:
        user_params[user_id] = DEFAULT_PARAMS.copy()

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
            
            # Get user-specific parameters
            params = user_params[user_id]
            
            # Process image for drawing with user parameters
            points = independencia_ou_morte(
                input_path=current_image_path,
                output_dir="steps",
                process_cell_size=params['process_cell_size'],
                points_cell_width=params['points_cell_width'],
                upper_left_edge=[170, 65, -118, -3, 88, -2],
                bottom_right_edge=[601, 403, -118, -3, 88, -2],
                z_up=params['z_up'],
                remove_background=params['remove_background'],  # Use the parameter value
                # Background removal parameters
                bg_threshold=params['bg_threshold'],
                bg_erode_pixels=params['bg_erode_pixels'],
                # Contour extraction parameters
                threshold1=params['threshold1'],
                threshold2=params['threshold2'],
                blur_size=params['blur_size'],
                # Path optimization parameters
                distance_threshold=params['distance_threshold'],
                epsilon=params['epsilon'],
                linewidth=params['linewidth']
            )

            # Send processed image preview
            if os.path.exists('steps/final_result.png'):
                await update.message.reply_photo(photo=open('steps/contour.png', 'rb'))
                await update.message.reply_photo(photo=open('steps/3d_path.png', 'rb'))
                await update.message.reply_photo(photo=open('steps/final_result.png', 'rb'))
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
    
    user_id = update.effective_user.id
    
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
        
        # Get user-specific parameters
        params = user_params[user_id]
        
        # Process image for drawing with user parameters
        points = independencia_ou_morte(
            input_path=current_image_path,
            output_dir="steps",
            process_cell_size=params['process_cell_size'],
            points_cell_width=params['points_cell_width'],
            upper_left_edge=[170, 65, -118, -3, 88, -2],
            bottom_right_edge=[601, 403, -118, -3, 88, -2],
            z_up=params['z_up'],
            remove_background=params['remove_background'],  # Use the parameter value
            # Background removal parameters
            bg_threshold=params['bg_threshold'],
            bg_erode_pixels=params['bg_erode_pixels'],
            # Contour extraction parameters
            threshold1=params['threshold1'],
            threshold2=params['threshold2'],
            blur_size=params['blur_size'],
            # Path optimization parameters
            distance_threshold=params['distance_threshold'],
            epsilon=params['epsilon'],
            linewidth=params['linewidth']
        )
        
        # Send processed image preview
        if os.path.exists('steps/final_result.png'):
            await update.message.reply_photo(photo=open('steps/contour.png', 'rb'))
            await update.message.reply_photo(photo=open('steps/3d_path.png', 'rb'))
            await update.message.reply_photo(photo=open('steps/final_result.png', 'rb'))
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

# New functions for parameter editing

async def params_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display current parameters and allow editing."""
    user_id = update.effective_user.id
    
    # Initialize parameters if not existing
    if user_id not in user_params:
        user_params[user_id] = DEFAULT_PARAMS.copy()
    
    # Create keyboard with parameter options
    keyboard = []
    for param_name, param_desc in EDITABLE_PARAMS:
        current_value = user_params[user_id][param_name]
        keyboard.append([InlineKeyboardButton(
            f"{param_name}: {current_value} - {param_desc}", 
            callback_data=f"edit_{param_name}"
        )])
    
    # Add reset option
    keyboard.append([InlineKeyboardButton("Reset to Default Values", callback_data="reset_params")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔧 Drawing Parameters\n\n"
        "These parameters control how the image is processed and drawn. "
        "Click on a parameter to edit its value:",
        reply_markup=reply_markup
    )
    
    return EDITING_PARAMS

async def param_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks for parameter editing."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "reset_params":
        # Reset to default values
        user_params[user_id] = DEFAULT_PARAMS.copy()
        
        await query.edit_message_text(
            "Parameters reset to default values. Use /params to view them."
        )
        return CHATTING
    
    elif data.startswith("edit_"):
        # Extract parameter name
        param_name = data.split("_")[1]
        
        # Find parameter description
        param_desc = next((desc for name, desc in EDITABLE_PARAMS if name == param_name), "")
        current_value = user_params[user_id][param_name]
        
        await query.edit_message_text(
            f"Editing parameter: {param_name}\n"
            f"Description: {param_desc}\n"
            f"Current value: {current_value}\n\n"
            f"Please enter the new integer value:"
        )
        
        # Store the parameter name being edited
        context.user_data['editing_param'] = param_name
        
        return WAITING_PARAM_VALUE
    
    return EDITING_PARAMS

async def save_param_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the new value for the parameter."""
    user_id = update.effective_user.id
    text = update.message.text
    
    param_name = context.user_data.get('editing_param')
    
    if not param_name:
        await update.message.reply_text("Error: No parameter selected. Please use /params to start again.")
        return CHATTING
    
    try:
        # Convert to integer
        new_value = int(text)
        
        # Special handling for remove_background parameter
        if param_name == 'remove_background':
            if new_value not in [0, 1]:
                await update.message.reply_text("❌ For remove_background, please enter 1 (yes) or 0 (no).")
                return WAITING_PARAM_VALUE
            new_value = bool(new_value)  # Convert to boolean
        
        # Update the parameter
        user_params[user_id][param_name] = new_value
        
        await update.message.reply_text(
            f"✅ Parameter '{param_name}' updated to {new_value}.\n\n"
            f"Use /params to view or edit other parameters."
        )
        
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid input. Please enter an integer value.\n"
            "Use /cancel to stop editing parameters."
        )
        return WAITING_PARAM_VALUE
    
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
                CommandHandler("params", params_command),  # New command for parameters
                CommandHandler("clear", clear_history),
                MessageHandler(filters.TEXT & ~filters.COMMAND, chat),
            ],
            GENERATING_IMAGE: [
                CommandHandler("cancel", cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, generate_image),
            ],
            UPLOAD_PHOTO: [
                CommandHandler("cancel", cancel),
                MessageHandler(filters.PHOTO, process_uploaded_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda update, context: 
                    update.message.reply_text("Please upload a photo or use /cancel to go back.")),
            ],
            DRAWING_CONFIRM: [
                CommandHandler("cancel", cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, draw_confirm),
            ],
            EDITING_PARAMS: [
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(param_button),
            ],
            WAITING_PARAM_VALUE: [
                CommandHandler("cancel", cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_param_value),
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