import asyncio
import aiohttp
import sqlite3
import os
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- .ENV YUKLASH ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# --- HOLATLAR (FSM) ---
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_ban = State()
    waiting_for_unban = State()

class UserStates(StatesGroup):
    setting_reminder = State()

# --- OB-HAVO TARJIMONI (INGLIZCHADAN O'ZBEKCHAGA) ---
WEATHER_UZ = {
    "clear sky": "Musaffo osmon",
    "few clouds": "Bir oz bulutli",
    "scattered clouds": "Tarqoq bulutlar",
    "broken clouds": "Parcha bulutlar",
    "overcast clouds": "Qalin bulutli",
    "light rain": "Yengil yomg'ir",
    "moderate rain": "O'rtacha yomg'ir",
    "heavy intensity rain": "Kuchli yomg'ir",
    "very heavy rain": "Juda kuchli yomg'ir",
    "extreme rain": "Jala",
    "freezing rain": "Muzli yomg'ir",
    "light intensity shower rain": "Yengil jala",
    "shower rain": "Jala",
    "heavy intensity shower rain": "Kuchli jala",
    "thunderstorm": "Momaqaldiroq",
    "snow": "Qor",
    "light snow": "Yengil qor",
    "heavy snow": "Qalin qor",
    "sleet": "Qor aralash yomg'ir",
    "mist": "Tuman",
    "fog": "Quyuq tuman",
    "haze": "G'ubor",
    "dust": "Chang",
    "smoke": "Tutun",
    "sand/ dust whirls": "Qumli bo'ron"
}

def get_desc(desc_en, lang):
    if lang == 'uz':
        # Agar so'z lug'atimizda bo'lsa o'zbekchasini beradi, bo'lmasa borini bosh harf bilan qaytaradi
        return WEATHER_UZ.get(desc_en.lower(), desc_en.capitalize())
    return desc_en.capitalize()

# --- HUDUDLAR RO'YXATI ---
UZB_REGIONS = {
    "Toshkent sh.": ["Tashkent"],
    "Surxondaryo": ["Termez", "Sariosiyo", "Denov", "Sherobod", "Boysun", "Qumqo'rg'on", "Sho'rchi", "Jarqo'rg'on", "Angor", "Muzrabot", "Qiziriq", "Bandixon", "Uzun", "Oltinsoy"],
    "Samarqand": ["Samarkand", "Urgut", "Kattaqo'rg'on", "Jomboy", "Toyloq", "Ishtixon", "Payariq", "Bulung'ur"],
    "Toshkent v.": ["Chirchiq", "Angren", "Olmaliq", "Nurafshon", "Zangiota", "Qibray", "Parkent", "Bo'stonliq"],
    "Farg'ona": ["Fergana", "Margilan", "Qo'qon", "Quva", "Rishton", "Beshariq", "Oltiariq"],
    "Andijon": ["Andijan", "Asaka", "Shahrixon", "Xo'jaobod", "Baliqchi", "Izboskan"],
    "Namangan": ["Namangan", "Chust", "Kosonsoy", "To'raqo'rg'on", "Uychi", "Pop"],
    "Buxoro": ["Bukhara", "G'ijduvon", "Vobkent", "Shofirkon", "Qorako'l", "Olot", "Romitan"],
    "Qashqadaryo": ["Karshi", "Shakhrisabz", "Kitob", "Qamashi", "Yakkabog'", "G'uzor", "Muborak", "Kasbi"],
    "Jizzax": ["Jizzakh", "Zomin", "G'allaorol", "Forish", "Do'stlik", "Paxtakor", "Zafarobod"],
    "Navoiy": ["Navoi", "Zarafshan", "Uchquduq", "Xatirchi", "Navbahor", "Nurota"],
    "Sirdaryo": ["Guliston", "Yangiyer", "Shirin", "Sirdaryo", "Boyovut", "Xavos"],
    "Xorazm": ["Urgench", "Khiva", "Xonqa", "Hazorasp", "Gurlan", "Bog'ot", "Shovot"],
    "Qoraqalpog'iston": ["Nukus", "Qo'ng'irot", "Beruniy", "To'rtko'l", "Chimboy", "Taxiatosh", "Amudaryo"]
}

# --- MA'LUMOTLAR BAZASI ---
def init_db():
    conn = sqlite3.connect('weather_bot.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        lang TEXT,
        city TEXT,
        is_banned INTEGER DEFAULT 0,
        reminder_time TEXT DEFAULT 'OFF',
        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('maintenance', '0')")
    conn.commit()
    conn.close()

def get_db_data(query, params=(), fetchone=True):
    conn = sqlite3.connect('weather_bot.db')
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = cursor.fetchone() if fetchone else cursor.fetchall()
    conn.close()
    return res

def update_db(query, params=()):
    conn = sqlite3.connect('weather_bot.db')
    conn.execute(query, params)
    conn.commit()
    conn.close()

def update_activity(user_id):
    update_db("UPDATE users SET last_active=CURRENT_TIMESTAMP WHERE user_id=?", (user_id,))

# --- MATNLAR ---
TEXTS = {
    'uz': {
        'start': "Assalomu alaykum! Tilni tanlang / Выберите язык / Choose language:",
        'send_loc_prompt': "📍 Pastdagi tugma orqali joylashuvingizni yuboring yoki ro'yxatdan viloyatni tanlang.",
        'region': "Viloyatni tanlang:",
        'district': "Tumanni tanlang:",
        'menu_btn': "Asosiy menyu",
        'now_btn': "🌡 Hozirgi ob-havo",
        'forecast_btn': "📅 5 kunlik prognoz",
        'reminder_btn': "⏰ Eslatma sozlash",
        'loc_btn': "📍 Lokatsiyani yuborish",
        'weather_now': "📍 {city}\n🌡 Harorat: {temp}°C\n☁️ Holat: {desc}\n💨 Shamol: {wind} m/s",
        'ask_time': "Eslatma vaqtini kiriting (masalan 08:00). O'chirish uchun 'OFF' deb yozing:",
        'banned': "🚫 Siz bloklangansiz.",
        'maintenance': "🛠 Botda texnik ishlar ketmoqda.",
        'not_found': "Shahar topilmadi."
    },
    'ru': {
        'start': "Здравствуйте! Выберите язык / Choose language:",
        'send_loc_prompt': "📍 Отправьте вашу локацию с помощью кнопки ниже или выберите область из списка.",
        'region': "Выберите область:",
        'district': "Выберите район:",
        'menu_btn': "Главное меню",
        'now_btn': "🌡 Погода сейчас",
        'forecast_btn': "📅 Прогноз на 5 дней",
        'reminder_btn': "⏰ Настройка уведомлений",
        'loc_btn': "📍 Отправить локацию",
        'weather_now': "📍 {city}\n🌡 Температура: {temp}°C\n☁️ Состояние: {desc}\n💨 Ветер: {wind} м/с",
        'ask_time': "Введите время (напр. 08:00). Для выкл. напишите 'OFF':",
        'banned': "🚫 Вы заблокированы.",
        'maintenance': "🛠 В боте технические работы.",
        'not_found': "Город не найден."
    },
    'en': {
        'start': "Hello! Choose language:",
        'send_loc_prompt': "📍 Send your location using the button below or select a region from the list.",
        'region': "Select a region:",
        'district': "Select a district:",
        'menu_btn': "Main Menu",
        'now_btn': "🌡 Current weather",
        'forecast_btn': "📅 5-day forecast",
        'reminder_btn': "⏰ Set Reminder",
        'loc_btn': "📍 Send location",
        'weather_now': "📍 {city}\n🌡 Temp: {temp}°C\n☁️ Condition: {desc}\n💨 Wind: {wind} m/s",
        'ask_time': "Enter time (e.g. 08:00). Type 'OFF' to disable:",
        'banned': "🚫 You are banned.",
        'maintenance': "🛠 Bot is under maintenance.",
        'not_found': "City not found."
    }
}

# --- KLAVIATURALAR ---
def lang_inline():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="setl_uz"),
         InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setl_ru"),
         InlineKeyboardButton(text="🇬🇧 English", callback_data="setl_en")]
    ])

def regions_inline():
    builder = []
    row = []
    for reg in UZB_REGIONS.keys():
        row.append(InlineKeyboardButton(text=reg, callback_data=f"setr_{reg}"))
        if len(row) == 2:
            builder.append(row); row = []
    if row: builder.append(row)
    return InlineKeyboardMarkup(inline_keyboard=builder)

def location_reply(lang):
    kb = [[KeyboardButton(text=TEXTS[lang]['loc_btn'], request_location=True)]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def main_reply(lang):
    kb = [
        [KeyboardButton(text=TEXTS[lang]['now_btn']), KeyboardButton(text=TEXTS[lang]['forecast_btn'])],
        [KeyboardButton(text=TEXTS[lang]['reminder_btn']), KeyboardButton(text=TEXTS[lang]['loc_btn'], request_location=True)],
        [KeyboardButton(text="🌐 Til / Язык / Lang")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_reply():
    kb = [
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Rassilka")],
        [KeyboardButton(text="💾 DB Yuklash"), KeyboardButton(text="📄 Excel Export")],
        [KeyboardButton(text="🚫 Ban"), KeyboardButton(text="♻️ Unban")],
        [KeyboardButton(text="🛠 Maintenance"), KeyboardButton(text="🔙 Foydalanuvchi menyusi")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- OB-HAVO FUNKSIYALARI ---
async def get_weather_data(city, lang, mode="weather"):
    url = f"https://api.openweathermap.org/data/2.5/{mode}?q={city}&appid={WEATHER_API_KEY}&units=metric&lang={lang}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            return await r.json()

# --- ADMIN HANDLERS ---
@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_start(message: types.Message):
    await message.answer("🛠 Admin panelga xush kelibsiz!", reply_markup=admin_reply())

@dp.message(F.text == "🔙 Foydalanuvchi menyusi", F.from_user.id == ADMIN_ID)
async def admin_back(message: types.Message):
    u = get_db_data("SELECT lang FROM users WHERE user_id=?", (message.from_user.id,))
    lang = u[0] if u else 'uz'
    await message.answer(TEXTS[lang]['menu_btn'], reply_markup=main_reply(lang))

@dp.message(F.text == "📊 Statistika", F.from_user.id == ADMIN_ID)
async def admin_stats(message: types.Message):
    total = get_db_data("SELECT COUNT(*) FROM users")[0]
    banned = get_db_data("SELECT COUNT(*) FROM users WHERE is_banned=1")[0]
    await message.answer(f"📊 **Statistika**\n👥 Jami foydalanuvchilar: {total}\n🚫 Bloklanganlar: {banned}", parse_mode="Markdown")

@dp.message(F.text == "💾 DB Yuklash", F.from_user.id == ADMIN_ID)
async def admin_db(message: types.Message):
    await message.answer_document(FSInputFile("weather_bot.db"))

@dp.message(F.text == "📄 Excel Export", F.from_user.id == ADMIN_ID)
async def admin_excel(message: types.Message):
    conn = sqlite3.connect('weather_bot.db')
    df = pd.read_sql_query("SELECT * FROM users", conn)
    df.to_excel("users.xlsx", index=False)
    conn.close()
    await message.answer_document(FSInputFile("users.xlsx"))

@dp.message(F.text == "🛠 Maintenance", F.from_user.id == ADMIN_ID)
async def admin_maint(message: types.Message):
    curr = get_db_data("SELECT value FROM settings WHERE key='maintenance'")[0]
    new = '1' if curr == '0' else '0'
    update_db("UPDATE settings SET value=? WHERE key='maintenance'", (new,))
    await message.answer(f"⚙️ Texnik xizmat: {'YOQILDI 🔴' if new=='1' else 'OCHILDI 🟢'}")

@dp.message(F.text == "📢 Rassilka", F.from_user.id == ADMIN_ID)
async def admin_broadcast_start(message: types.Message, state: FSMContext):
    await message.answer("Rassilka xabarini yuboring (Rasm, Video yoki Matn):")
    await state.set_state(AdminStates.waiting_for_broadcast)

@dp.message(AdminStates.waiting_for_broadcast, F.from_user.id == ADMIN_ID)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    users = get_db_data("SELECT user_id FROM users WHERE is_banned=0", fetchone=False)
    count = 0
    for u in users:
        try:
            await message.copy_to(u[0])
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await state.clear()
    await message.answer(f"✅ Xabar {count} ta odamga yetib bordi.")

@dp.message(F.text == "🚫 Ban", F.from_user.id == ADMIN_ID)
async def admin_ban_start(message: types.Message, state: FSMContext):
    await message.answer("Bloklash uchun ID raqamini yuboring:")
    await state.set_state(AdminStates.waiting_for_ban)

@dp.message(AdminStates.waiting_for_ban, F.from_user.id == ADMIN_ID)
async def admin_ban_do(message: types.Message, state: FSMContext):
    try:
        update_db("UPDATE users SET is_banned=1 WHERE user_id=?", (int(message.text),))
        await message.answer(f"✅ {message.text} bloklandi.")
    except: await message.answer("Xato ID.")
    await state.clear()

@dp.message(F.text == "♻️ Unban", F.from_user.id == ADMIN_ID)
async def admin_unban_start(message: types.Message, state: FSMContext):
    await message.answer("Blokdan chiqarish uchun ID yuboring:")
    await state.set_state(AdminStates.waiting_for_unban)

@dp.message(AdminStates.waiting_for_unban, F.from_user.id == ADMIN_ID)
async def admin_unban_do(message: types.Message, state: FSMContext):
    try:
        update_db("UPDATE users SET is_banned=0 WHERE user_id=?", (int(message.text),))
        await message.answer(f"✅ {message.text} blokdan chiqarildi.")
    except: await message.answer("Xato ID.")
    await state.clear()

# --- FOYDALANUVCHI HANDLERS ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    exists = get_db_data("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not exists:
        update_db("INSERT INTO users (user_id) VALUES (?)", (user_id,))
    
    await message.answer(TEXTS['uz']['start'], reply_markup=lang_inline())

@dp.message(F.text == "🌐 Til / Язык / Lang")
async def change_lang_btn(message: types.Message):
    await message.answer("Tilni tanlang / Выберите язык / Choose language:", reply_markup=lang_inline())

@dp.callback_query(F.data.startswith("setl_"))
async def set_lang(callback: types.CallbackQuery):
    lang = callback.data.split("_")[1]
    update_db("UPDATE users SET lang=? WHERE user_id=?", (lang, callback.from_user.id))
    await callback.message.delete()
    
    await callback.message.answer(TEXTS[lang]['send_loc_prompt'], reply_markup=location_reply(lang))
    await callback.message.answer(TEXTS[lang]['region'], reply_markup=regions_inline())

@dp.callback_query(F.data.startswith("setr_"))
async def set_region(callback: types.CallbackQuery):
    reg = callback.data.split("_")[1]
    builder = []
    for dist in UZB_REGIONS[reg]:
        builder.append([InlineKeyboardButton(text=dist, callback_data=f"setd_{dist}")])
    await callback.message.edit_text(TEXTS['uz']['district'], reply_markup=InlineKeyboardMarkup(inline_keyboard=builder))

@dp.callback_query(F.data.startswith("setd_"))
async def set_district(callback: types.CallbackQuery):
    dist = callback.data.split("_")[1]
    user_id = callback.from_user.id
    update_db("UPDATE users SET city=? WHERE user_id=?", (dist, user_id))
    u = get_db_data("SELECT lang FROM users WHERE user_id=?", (user_id,))
    await callback.message.delete()
    
    await callback.message.answer(TEXTS[u[0]]['menu_btn'], reply_markup=main_reply(u[0]))

# --- LOKATSIYA ORQALI ANIQLASH ---
@dp.message(F.location)
async def handle_location(message: types.Message):
    user_id = message.from_user.id
    u = get_db_data("SELECT lang, is_banned FROM users WHERE user_id=?", (user_id,))
    if not u: return
    if u[1]: return await message.answer(TEXTS[u[0]]['banned'])
    update_activity(user_id)
    
    lat = message.location.latitude
    lon = message.location.longitude
    lang = u[0]
    
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang={lang}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            data = await r.json()
            
    if data.get("main"):
        update_db("UPDATE users SET city=? WHERE user_id=?", (data['name'], user_id))
        
        # Tarjimon funksiyasidan foydalanamiz
        translated_desc = get_desc(data['weather'][0]['description'], lang)
        
        text = TEXTS[lang]['weather_now'].format(
            city=data['name'], temp=round(data['main']['temp']),
            desc=translated_desc, wind=data['wind']['speed']
        )
        await message.answer(text, reply_markup=main_reply(lang))
    else:
        await message.answer(TEXTS[lang]['not_found'])

# --- ASOSIY MENYU TUGMALARI ---
@dp.message(F.text.in_([TEXTS['uz']['now_btn'], TEXTS['ru']['now_btn'], TEXTS['en']['now_btn']]))
async def weather_now(message: types.Message):
    user_id = message.from_user.id
    update_activity(user_id)
    u = get_db_data("SELECT lang, city, is_banned FROM users WHERE user_id=?", (user_id,))
    if u[2]: return await message.answer(TEXTS[u[0]]['banned'])
    if get_db_data("SELECT value FROM settings WHERE key='maintenance'")[0] == '1' and user_id != ADMIN_ID:
        return await message.answer(TEXTS[u[0]]['maintenance'])
        
    data = await get_weather_data(u[1], u[0])
    if data.get("main"):
        translated_desc = get_desc(data['weather'][0]['description'], u[0])
        
        text = TEXTS[u[0]]['weather_now'].format(
            city=data['name'], temp=round(data['main']['temp']),
            desc=translated_desc, wind=data['wind']['speed']
        )
        await message.answer(text)
    else:
        await message.answer(TEXTS[u[0]]['not_found'])

@dp.message(F.text.in_([TEXTS['uz']['forecast_btn'], TEXTS['ru']['forecast_btn'], TEXTS['en']['forecast_btn']]))
async def weather_forecast(message: types.Message):
    user_id = message.from_user.id
    update_activity(user_id)
    u = get_db_data("SELECT lang, city, is_banned FROM users WHERE user_id=?", (user_id,))
    if u[2]: return
    
    data = await get_weather_data(u[1], u[0], mode="forecast")
    if data.get('list'):
        res = f"📅 {u[1]} - 5 kunlik prognoz:\n"
        for i in range(0, 40, 8):
            day = data['list'][i]
            date = day['dt_txt'].split(" ")[0]
            translated_desc = get_desc(day['weather'][0]['description'], u[0])
            
            res += f"\n🔹 {date}: {round(day['main']['temp'])}°C, {translated_desc}"
        await message.answer(res)
    else:
        await message.answer(TEXTS[u[0]]['not_found'])

# Eslatma sozlash
@dp.message(F.text.in_([TEXTS['uz']['reminder_btn'], TEXTS['ru']['reminder_btn'], TEXTS['en']['reminder_btn']]))
async def reminder_start(message: types.Message, state: FSMContext):
    u = get_db_data("SELECT lang FROM users WHERE user_id=?", (message.from_user.id,))
    await message.answer(TEXTS[u[0]]['ask_time'])
    await state.set_state(UserStates.setting_reminder)

@dp.message(UserStates.setting_reminder)
async def reminder_save(message: types.Message, state: FSMContext):
    update_db("UPDATE users SET reminder_time=? WHERE user_id=?", (message.text, message.from_user.id))
    await state.clear()
    await message.answer(f"✅: {message.text}")

# --- SCHEDULER (HAR KUNLIK XABARNOMA) ---
async def check_reminders():
    now = datetime.now().strftime("%H:%M")
    users = get_db_data("SELECT user_id, lang, city FROM users WHERE reminder_time=?", (now,), fetchone=False)
    for u in users:
        data = await get_weather_data(u[2], u[1])
        if data.get("main"):
            translated_desc = get_desc(data['weather'][0]['description'], u[1])
            
            text = f"🔔 Kunlik eslatma!\n" + TEXTS[u[1]]['weather_now'].format(
                city=data['name'], temp=round(data['main']['temp']),
                desc=translated_desc, wind=data['wind']['speed']
            )
            try: await bot.send_message(u[0], text)
            except: pass

async def main():
    init_db()
    scheduler.add_job(check_reminders, "interval", minutes=1)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
        
