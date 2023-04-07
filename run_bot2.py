import requests
import time
import telegram
import threading
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, Updater, Dispatcher
from config import sent_feedbacks, api_key_gpt
from event_system import EventSystem

NEW_FEEDBACK_EVENT = 'new_feedback'
api_url = 'https://feedbacks-api.wildberries.ru/api/v1/feedbacks'

def run_bot2(update: Update, context: CallbackContext, api_key_wb: str, signature: str, bot: telegram.Bot, stop_flag: bool, event_system: EventSystem):
    # event_system = EventSystem()
    t = threading.Thread(target=actual_run_bot2, args=(update, context, api_key_wb, signature, bot, stop_flag, event_system))
    context.user_data['api_key_wb'] = api_key_wb
    context.user_data['signature'] = signature
    context.user_data['bot'] = bot
    context.user_data['stop_flag'] = stop_flag
    t.start()

def actual_run_bot2(update: Update, context: CallbackContext, api_key_wb: str, signature: str, bot: telegram.Bot, stop_flag: bool, event_system: EventSystem):
    context.user_data['stop_flag'] = False
    # функция для создания запроса к API магазина
    def make_request(url, method='GET', data=None):
        headers = {'Authorization': api_key_wb, 'accept': 'application/json'}
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'PATCH':
                response = requests.patch(url, headers=headers, json=data)
            else:
                response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            print(f'Ошибка запроса {method} {url}: {err}')
        except Exception as err:
            print(f'Ошибка при запросе {method} {url}: {err}')
        return None

    # функция для получения отзывов из API магазина
    def get_wildberries_feedbacks(take=5, skip=0, is_answered=False, order="dateDesc"):
        url = f"{api_url}?take={take}&skip={skip}&isAnswered={is_answered}&order={order}"
        return make_request(url)

    # функция для отправки ответа на отзыв через API магазина
    def send_reply(review_id, reply_text):
        reviews_url = api_url
        data = {
            'id': review_id,
            'wasViewed': True,
            'text': reply_text
        }
        make_request(reviews_url, method='PATCH', data=data)

    # функция для отправки текста на генерацию модели GPT-3.5
    def send_to_gpt(review_text, api_key_gpt):
        url = 'https://api.openai.com/v1/chat/completions'
        headers = {'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + api_key_gpt}
        
        instructions = ( "Определить тональность отзыва: положительная, негативная или нейтральная. "
            "Ответить на отзыв в соответствии с алгоритмом, представленным для каждого типа отзыва, и от лица команды.\n"
            "На все отзывы отвечать с ноткой юмора. Никогда не рекомендовать товары других брендов.\n\n"
            
            "Положительный отзыв:\n"
            "a. Выразить благодарность за отзыв.\n"
            "b. Указать, что вам приятно, что клиент остался доволен.\n"
            "c. Завершить ответ с дружелюбными пожеланиями.\n\n"
            
            "Негативный отзыв:\n"
            "a. Выразить сожаление о возникших неудобствах или проблемах.\n"
            "b. Указать, что вы принимаете к сведению их замечания.\n"
            "c. обратить с пользу нашего товара\n"
            "d. Завершить ответ с извинениями и обещанием улучшить качество продукта или услуги.\n\n"
            
            "Нейтральный отзыв:\n"
            "a. Поблагодарить за отзыв и обратить внимание на конкретные замечания.\n"
            "b. Если имеются предложения по улучшению, указать, что вы их примут во внимание.\n"
            "c. Завершить ответ с пожеланиями успеха и приятного дня."
            )
        
        prompt = f"Новый отзыв: {review_text}\nОтвет:"

        data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": review_text},
                {"role": "assistant", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 256,
        }
        generated_text = ''
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()  # генерируем исключение, если статус ответа не 200
            generated_text = response.json()['choices'][0]['message']['content']
            return f'{generated_text.strip()} {signature}'
        except requests.exceptions.HTTPError as err:
            print(f'Ошибка запроса: {err}')
        return f'{generated_text.strip()} {signature}'

    def handle_new_feedbacks(bot: telegram.Bot, signature: str):
        chat_id = update.effective_chat.id
        while not context.user_data['stop_flag']:
            if context.user_data['stop_flag']:
                break
            try:
                feedbacks = get_wildberries_feedbacks()
                if feedbacks and isinstance(feedbacks, dict):
                    for feedback in feedbacks['data']['feedbacks']:
                        if feedback.get('state') == 'none' and feedback.get('id') not in sent_feedbacks:
                            review_id = feedback.get('id')
                            sent_feedbacks.add(review_id)  # добавляем ID отзыва в список отправленных
                            review_text = feedback.get('text')
                            reply_text = send_to_gpt(review_text, api_key_gpt)

                            # Создаем InlineKeyboardMarkup с двумя callback кнопками
                            keyboard = [
                                [
                                    InlineKeyboardButton("Отправить", callback_data=f'send_{review_id}'),
                                    InlineKeyboardButton("Редактировать", callback_data=f'edit_{review_id}')
                                ]
                            ]
                            reply_markup = InlineKeyboardMarkup(keyboard)

                            # Отправляем сообщение с сгенерированным ответом и кнопками
                            bot.send_message(chat_id=chat_id, text=f'Новый отзыв:\n{review_text}\nОтвет: {reply_text}', reply_markup=reply_markup)

                time.sleep(12)
            except Exception as e:
                print(f'Произошла ошибка при выполнении запроса: {str(e)}')
    # handle_new_feedbacks(bot, signature)
    t = threading.Thread(target=handle_new_feedbacks, args=(bot, signature))
    t.start()

    def button_callback(update: Update, context: CallbackContext):
        query = update.callback_query
        action, _, review_id = query.data.partition("_")

        # Получаем текст сообщения, отправленного ботом
        reply_text = query.message.text.split("Ответ: ")[1]

        if action == "send":
            send_reply(review_id, reply_text)
            sent_feedbacks.discard(review_id)  # удаляем ID отзыва из списка отправленных после отправки ответа в магазин
            query.edit_message_text(text=f"Ответ отправлен на отзыв {review_id}:\n{reply_text}")
            event_system.trigger_event(NEW_FEEDBACK_EVENT, update, context)
        elif action == "edit":
            context.user_data['editing_review_id'] = review_id
            query.edit_message_text(text=f"Пожалуйста, скопируйте этот текст, внесите изменения и отправьте:\nОтвет на отзыв {review_id}: {reply_text}")
        # event_system.trigger_event('text_callback', update, context)
    # button_callback_handler = CallbackQueryHandler(button_callback, pattern='^(send_|edit_)')
    # context.dispatcher.add_handler(button_callback_handler)

    def text_callback(update: Update, context: CallbackContext):
        if 'editing_review_id' in context.user_data:
            message_text = update.message.text
            if message_text.startswith(f"Ответ на отзыв {context.user_data['editing_review_id']}"):
                custom_reply = message_text.split(f"Ответ на отзыв {context.user_data['editing_review_id']}: ")[1]
                send_reply(context.user_data['editing_review_id'], custom_reply)
                sent_feedbacks.discard(context.user_data['editing_review_id'])  # удаляем ID отзыва из списка отправленных после отправки отредактированного ответа в магазин
                update.message.reply_text(f"Ответ отправлен на отзыв {context.user_data['editing_review_id']}:\n{custom_reply}")
                del context.user_data['editing_review_id']
                event_system.trigger_event(NEW_FEEDBACK_EVENT, update, context)
        # event_system.trigger_event('button_callback', update, context)
    # text_callback_handler = MessageHandler(Filters.text & ~Filters.command, text_callback)
    # context.dispatcher.add_handler(text_callback_handler)
    event_system.add_listener('button_callback', button_callback)
    event_system.add_listener('text_callback', text_callback)
    event_system.add_listener(NEW_FEEDBACK_EVENT, handle_new_feedbacks)
    handle_new_feedbacks(bot, signature)