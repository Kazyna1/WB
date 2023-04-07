import telegram
import requests
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, Dispatcher, CallbackQueryHandler, MessageHandler, Filters, ConversationHandler, MessageFilter, CallbackContext
from run_bot import run_bot
from run_bot2 import run_bot2
from config import bot_token, user_data
from event_system import EventSystem

# параметры подключения к Telegram Bot API
bot = telegram.Bot(token=bot_token)
# event_system = EventSystem()

signature = "С заботой, команда Lili Profi"
global stop_flag
stop_flag = False

class WaitForSignatureFilter(MessageFilter):
    def filter(self, message):
        chat_id = message.chat_id
        return chat_id in user_data and 'api_key_wb' in user_data[chat_id] and 'signature' not in user_data[chat_id]

# функция стартового приветствия
def start(update, context):
    chat_id = update.message.chat_id
    welcome_text = "Привет! Я бот, который отвечает на отзывы из интернет-магазина. " \
                   "Когда появится новый отзыв, я отправлю его тебе в этот чат, " \
                   "и ты должен будешь написать ответ на него. " \
                   "Я помогу тебе сгенерировать текст ответа на основе текста отзыва. " \
                   "Пришли мне команду /help, если нужна помощь."

    context.bot.send_message(chat_id=chat_id, text=welcome_text)
    enter_api_key_wb(update, context)

# функция ввода API-ключа Wildberries
def enter_api_key_wb(update, context):
    if update.message:
        chat_id = update.message.chat_id
    else:
        chat_id = update.callback_query.message.chat_id

    message = "Введите свой API-ключ Wildberries:"
    context.bot.send_message(chat_id=chat_id, text=message)

    return 'API_KEY_WB'

# функция обработки введенного API-ключа Wildberries
def api_key_wb_handler(update, context):
    chat_id = update.message.chat_id
    
    if chat_id not in user_data:
        user_data[chat_id] = {}

    if 'api_key_wb' not in user_data[chat_id]:
        user_data[chat_id]['api_key_wb'] = update.message.text
        enter_signature(update, context)
        return 'SIGNATURE'
    else:
        user_data[chat_id]['signature'] = update.message.text
        signature_handler_new(update, context)
        return 'REVIEW_MODE'

# функция ввода подписи
def enter_signature(update, context):
    if update.message:
        chat_id = update.message.chat_id
    else:
        chat_id = update.callback_query.message.chat_id

    message = "Введите свою подпись:"
    context.bot.send_message(chat_id=chat_id, text=message)

    return 'SIGNATURE'

# функция обработки введенной подписи
def signature_handler_new(update, context):
    global signature
    signature = update.message.text
    chat_id = update.message.chat_id
    user_data[chat_id]['signature'] = update.message.text
    update.message.reply_text("Подпись успешно изменена!")

    review_mode_keyboard = [
        [
            InlineKeyboardButton("Ручной режим", callback_data='manual_mode'),
            InlineKeyboardButton("Автоматический режим", callback_data='auto_mode')
        ],
        [InlineKeyboardButton("Вернуться назад", callback_data='go_back')]
    ]
    reply_markup = InlineKeyboardMarkup(review_mode_keyboard)

    message = "Выберите режим отправки отзывов:"
    context.bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup)

    return 'REVIEW_MODE'

# функция обработки кнопки "Вернуться назад"
def go_back_handler(update, context):
    query = update.callback_query
    chat_id = query.message.chat_id
    context.bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
    enter_api_key_wb(update, context)

    return 'API_KEY_WB'

# функция обработки выбора режима отправки отзывов
def review_mode_handler(update, context):
    query = update.callback_query
    chat_id = query.message.chat_id
    if query.data == 'manual_mode':
        user_data[chat_id]['review_mode'] = 'manual'
    elif query.data == 'auto_mode':
        user_data[chat_id]['review_mode'] = 'auto'
    elif query.data == 'change_signature':
        enter_signature(update, context)
        return 'SIGNATURE'

    bot_start_keyboard = [
        [
            InlineKeyboardButton("Запустить бота", callback_data='start_bot'),
            InlineKeyboardButton("Вернуться в предыдущее меню", callback_data='change_review_mode')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(bot_start_keyboard)

    message = "Готовы запустить бота?"
    context.bot.edit_message_text(chat_id=chat_id, message_id=query.message.message_id, text=message, reply_markup=reply_markup)

    return 'BOT_START'

# функция обработки выбора запуска бота или изменения режима отправки отзывов
def bot_start_handler(update, context, event_system):
    query = update.callback_query
    chat_id = query.message.chat_id
    mode_text = "ручном" if user_data[chat_id]['review_mode'] == 'manual' else "автоматическом"
    if query.data == 'start_bot':
        context.bot.edit_message_text(chat_id=chat_id, message_id=query.message.message_id, text=f"Бот запущен в {mode_text} режиме.")
        api_key_wb = user_data[chat_id]['api_key_wb']
        signature = user_data[chat_id]['signature']
        if user_data[chat_id]['review_mode'] == 'manual':
            run_bot2(update, context, api_key_wb, signature, bot, stop_flag, event_system)  # Запуск run_bot2.py для ручного режима
        else:
            run_bot(update, context, api_key_wb, signature, bot, stop_flag)  # Запуск run_bot.py для автоматического режима
    elif query.data == 'change_review_mode':
        review_mode_handler(update, context)
    return 'REVIEW_MODE'

def handle_button_callback(update: Update, context: CallbackContext, event_system: EventSystem):
    event_system.trigger_event('button_callback', update, context)

def handle_text_callback(update: Update, context: CallbackContext, event_system: EventSystem):
    event_system.trigger_event('text_callback', update, context)

# функция остановки бота
def stop(update: Update, context: CallbackContext):
     context.user_data['stop_flag'] = True
     update.message.reply_text("Бот остановлен.")
    
     stop_keyboard = [
         [
             InlineKeyboardButton("Изменить API-ключ Wildberries", callback_data='change_api_key_wb'),
             InlineKeyboardButton("Изменить подпись", callback_data='change_signature')
         ],
         [InlineKeyboardButton("Продолжение работы бота", callback_data='continue_bot')]
     ]
     reply_markup = InlineKeyboardMarkup(stop_keyboard)
     chat_id = update.effective_chat.id
     context.bot.send_message(chat_id=chat_id, text="Выберите один из вариантов:", reply_markup=reply_markup)

     return 'STOP'

# функция обработки выбора действия после остановки бота
def stop_handler(update, context, event_system):
    global stop_flag
    query = update.callback_query
    chat_id = query.message.chat_id

    if query.data == 'change_api_key_wb':
        stop_flag = False
        enter_api_key_wb(update, context)
        return 'API_KEY_WB'
    elif query.data == 'change_signature':
        stop_flag = False
        enter_signature(update, context)
        return 'SIGNATURE'
    elif query.data == 'continue_bot':
        stop_flag = False
        context.bot.edit_message_text(chat_id=chat_id, message_id=query.message.message_id, text="Бот продолжает работу.")
        api_key_wb = user_data[chat_id]['api_key_wb']
        signature = user_data[chat_id]['signature']
        if user_data[chat_id]['review_mode'] == 'manual':
            run_bot2(update, context, api_key_wb, signature, bot, stop_flag, event_system)  # Запуск run_bot2.py для ручного режима
        else:
            run_bot(update, context, api_key_wb, signature, bot, stop_flag)  # Запуск run_bot.py для автоматического режима
    return 'STOP'

# функция помощи
def help_command(update, context):
    chat_id = update.message.chat_id
    help_text = "Чтобы остановить бота, отправьте команду /stop.\n Вы сможете изменить API-ключ Wildberries, подпись или продолжить работу бота."
    context.bot.send_message(chat_id=chat_id, text=help_text)

def main():
    event_system = EventSystem()
    updater = telegram.ext.Updater(token=bot_token, use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, api_key_wb_handler, pass_user_data=True, pass_chat_data=True))
    dispatcher.add_handler(MessageHandler(WaitForSignatureFilter(), signature_handler_new, pass_user_data=True, pass_chat_data=True))
    dispatcher.add_handler(CallbackQueryHandler(review_mode_handler, pattern='^(manual_mode|auto_mode|change_signature)$', pass_user_data=True, pass_chat_data=True))
    dispatcher.add_handler(CallbackQueryHandler(lambda update, context: bot_start_handler(update, context, event_system), pattern='^(start_bot|change_review_mode)$', pass_user_data=True, pass_chat_data=True))
    dispatcher.add_handler(CommandHandler("stop", stop))
    dispatcher.add_handler(CallbackQueryHandler(stop_handler, pattern='^(change_api_key_wb|change_signature|continue_bot)$', pass_user_data=True, pass_chat_data=True))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CallbackQueryHandler(go_back_handler, pattern='^go_back$'))
    dispatcher.add_handler(CallbackQueryHandler(lambda update, context: handle_button_callback(update, context, event_system), pattern='^(send_|edit_)'))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, lambda update, context: handle_text_callback(update, context, event_system)))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()