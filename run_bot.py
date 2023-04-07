import requests
import time
import telegram
import threading
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CommandHandler
from config import api_key_gpt

api_url = 'https://feedbacks-api.wildberries.ru/api/v1/feedbacks'

def run_bot(update: Update, context: CallbackContext, api_key_wb: str, signature: str, bot: telegram.Bot, stop_flag: bool, main_stop_function):
    t = threading.Thread(target=actual_run_bot, args=(update, context, api_key_wb, signature, bot, stop_flag, main_stop_function))
    context.user_data['api_key_wb'] = api_key_wb
    context.user_data['signature'] = signature
    context.user_data['bot'] = bot
    context.user_data['stop_flag'] = stop_flag
    t.start()

def actual_run_bot(update: Update, context: CallbackContext, api_key_wb: str, signature: str, bot: telegram.Bot, stop_flag: bool, main_stop_function):
    stop_flag = False
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
            # print(response.json())
            return response.json()
        except requests.exceptions.HTTPError as err:
            print(f'Ошибка запроса {method} {url}: {err}')
        except Exception as err:
            print(f'Ошибка при запросе {method} {url}: {err}')
        return None

    # функция для получения отзывов из API магазина
    def get_wildberries_feedbacks(take=1, skip=0, is_answered=False, order="dateDesc"):
        is_answered_str = "true" if is_answered else "false"
        url = f"{api_url}?take={take}&skip={skip}&isAnswered={is_answered_str}&order={order}"
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
        
        instructions = (
            "Определить тональность отзыва: положительная, негативная или нейтральная. "
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
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()  # генерируем исключение, если статус ответа не 200
            generated_text = response.json()['choices'][0]['message']['content']
            return f'{generated_text.strip()} {signature}'
        except requests.exceptions.HTTPError as err:
            print(f'Ошибка запроса: {err}')
        return f'{generated_text.strip()} {signature}'

    def stop_callback(update: Update, context: CallbackContext):
        if 'stop_flag' in context.user_data:
            main_stop_function()
            context.user_data['stop_flag'] = True
            update.message.reply_text("Бот остановлен.")
    stop_handler = CommandHandler('stop', stop_callback)
    context.dispatcher.add_handler(stop_handler)

    def handle_new_feedbacks(bot: telegram.Bot, signature: str):
        chat_id = update.effective_chat.id
        while not context.user_data['stop_flag']:
            if context.user_data['stop_flag']:
                break
            try:
                feedbacks = get_wildberries_feedbacks()
                if feedbacks and isinstance(feedbacks, dict):
                    for feedback in feedbacks['data']['feedbacks']:
                        if stop_flag:
                            break
                        if feedback.get('state') == 'none':
                            review_id = feedback.get('id')
                            review_text = feedback.get('text')
                            reply_text = send_to_gpt(review_text, api_key_gpt)
                            send_reply(review_id, reply_text)
                            bot.send_message(chat_id=chat_id, text=f'Новый отзыв:\n{review_text}\nОтвет: {reply_text}')
                time.sleep(10)
            except Exception as e:
                print(f'Произошла ошибка при выполнении запроса: {str(e)}')
    handle_new_feedbacks(bot, signature)