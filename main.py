import asyncio
import aiohttp
import sqlite3
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# --- VILOYAT VA TUMANLAR RO'YXATI ---
UZB_REGIONS = {
    "Toshkent sh.": ["Tashkent"],
    "Surxondaryo": ["Termez", "Sariosiyo", "Denov", "Sherobod", "Boysun", "Qumqo'rg'on", "Sho'rchi", "Jarqo'rg'on", "Angor", "Muzrabot", "Qiziriq", "Bandixon", "Uzun", "Oltinsoy"],
    "Toshkent v.": ["Chirchiq", "Angren", "Olmaliq", "Nurafshon", "Zangiota", "Qibray", "Parkent", "Bo'stonliq"],
    "Samarqand": ["Samarkand", "Urgut", "Kattaqo'rg'on", "Jomboy", "Toyloq", "Ishtixon", "Payariq", "Bulung'ur"],
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
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, lang TEXT DEFAULT 'uz', city TEXT DEFAULT 'Tashkent')''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('weather_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT lang, city FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if user is None:
        cursor.execute('INSERT INTO users (user_id, lang, city) VALUES (?, ?, ?)', (user_id, 'uz', 'Tashkent'))
        conn.commit()
        user = ('uz', 'Tashkent')
    conn.close()
    return {'lang': user[0], 'city': user[1]}

def update_user_city(user_id, city):
    conn = sqlite3.connect('weather_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET city = ? WHERE user_id = ?', (city, user_id))
    conn.commit()
    conn.close()

def update_user_lang(user_id, lang):
    conn = sqlite3.connect('weather_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET lang = ? WHERE user_id = ?', (lang, user_id))
    conn.commit()
    conn.close()

# --- KLAVIATURALAR ---
TEXTS = {
    'uz': {
        'start_msg': "Assalomu alaykum! Hududingizni tanlang yoki pastdagi tugma orqali lokatsiya yuboring:",
        'loc_btn': "📍 Lokatsiyani yuborish",
        'lang_btn': "🌐 Tilni o'zgartirish",
        'city_btn': "🏢 Hududni o'zgartirish",
        'weather': "📍 {city} ob-havosi:\n🌡 Harorat: {temp}°C\n☁️ Holat: {desc}\n💨 Shamol: {wind} m/s",
        'not_found': "Ma'lumot topilmadi."
    },
    'ru': {
        'start_msg': "Здравствуйте! Выберите регион или отправьте локацию:",
        'loc_btn': "📍 Отправить локацию",
        'lang_btn': "🌐 Изменить язык",
        'city_btn': "🏢 Изменить регион",
        'weather': "📍 Погода в {city}:\n🌡 Температура: {temp}°C\n☁️ Состояние: {desc}\n💨 Ветер: {wind} м/с",
        'not_found': "Данные не найдены."
    }
}

def main_reply_kb(lang='uz'):
    kb = [
        [KeyboardButton(text=TEXTS[lang]['loc_btn'], request_location=True)],
        [KeyboardButton(text=TEXTS[lang]['city_btn']), KeyboardButton(text=TEXTS[lang]['lang_btn'])]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def regions_kb():
    builder = []
    row = []
    for region in UZB_REGIONS.keys():
        row.append(InlineKeyboardButton(text=region, callback_data=f"region_{region}"))
        if len(row) == 2:
            builder.append(row)
            row = []
    if row: builder.append(row)
    return InlineKeyboardMarkup(inline_keyboard=builder)

def districts_kb(region_name):
    builder = []
    row = []
    for district in UZB_REGIONS[region_name]:
        row.append(InlineKeyboardButton(text=district, callback_data=f"dist_{district}"))
        if len(row) == 2:
            builder.append(row)
            row = []
    if row: builder.append(row)
    builder.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_regions")])
    return InlineKeyboardMarkup(inline_keyboard=builder)

def lang_inline_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"), InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")]
    ])

# --- OB-HAVO SO'ROVI ---
async def fetch_weather(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

# --- ASOSIY FUNKSIYALAR ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_data = get_user(message.from_user.id)
    lang = user_data['lang']
    # Pastki klaviaturani ham, ichki (inline) klaviaturani ham bittada chiqaramiz
    await message.answer("Tizimga xush kelibsiz!", reply_markup=main_reply_kb(lang))
    await message.answer(TEXTS[lang]['start_msg'], reply_markup=regions_kb())

# Til tugmasi
@dp.message(F.text.in_(["🌐 Tilni o'zgartirish", "🌐 Изменить язык"]))
async def change_lang_cmd(message: types.Message):
    await message.answer("Tilni tanlang / Выберите язык:", reply_markup=lang_inline_kb())

# Hudud tugmasi
@dp.message(F.text.in_(["🏢 Hududni o'zgartirish", "🏢 Изменить регион"]))
async def change_city_cmd(message: types.Message):
    user_data = get_user(message.from_user.id)
    await message.answer(TEXTS[user_data['lang']]['start_msg'], reply_markup=regions_kb())

# Til tanlash reaksiyasi
@dp.callback_query(F.data.startswith('lang_'))
async def process_lang(callback: types.CallbackQuery):
    lang = callback.data.split('_')[1]
    update_user_lang(callback.from_user.id, lang)
    await callback.message.delete()
    await callback.message.answer(TEXTS[lang]['start_msg'], reply_markup=regions_kb())
    # Klaviaturani yangilash uchun bildirishnoma
    await callback.message.answer("Til o'zgardi", reply_markup=main_reply_kb(lang))

# Viloyat tanlash reaksiyasi
@dp.callback_query(F.data.startswith('region_'))
async def process_region(callback: types.CallbackQuery):
    region_name = callback.data.split('_')[1]
    await callback.message.edit_text(f"🏙 {region_name} tumanlari:", reply_markup=districts_kb(region_name))

# Orqaga qaytish reaksiyasi
@dp.callback_query(F.data == "back_regions")
async def process_back(callback: types.CallbackQuery):
    user_data = get_user(callback.from_user.id)
    await callback.message.edit_text(TEXTS[user_data['lang']]['start_msg'], reply_markup=regions_kb())

# Tuman tanlash reaksiyasi (Ob-havoni chiqarish)
@dp.callback_query(F.data.startswith('dist_'))
async def process_district(callback: types.CallbackQuery):
    district_name = callback.data.split('_')[1]
    user_id = callback.from_user.id
    update_user_city(user_id, district_name)
    user_data = get_user(user_id)
    lang = user_data['lang']
    
    await callback.message.delete()
    url = f"https://api.openweathermap.org/data/2.5/weather?q={district_name}&appid={WEATHER_API_KEY}&units=metric&lang={lang}"
    data = await fetch_weather(url)
    
    if data.get("main"):
        text = TEXTS[lang]['weather'].format(
            city=data['name'], temp=round(data['main']['temp']),
            desc=data['weather'][0]['description'].capitalize(), wind=data['wind']['speed']
        )
        await callback.message.answer(text, reply_markup=main_reply_kb(lang))
    else:
        await callback.message.answer(TEXTS[lang]['not_found'])

# Lokatsiya yuborganda ishlaydigan reaksiya
@dp.message(F.location)
async def handle_loc(message: types.Message):
    user_id = message.from_user.id
    lang = get_user(user_id)['lang']
    lat, lon = message.location.latitude, message.location.longitude
    
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang={lang}"
    data = await fetch_weather(url)
    
    if data.get("main"):
        update_user_city(user_id, data['name'])
        text = TEXTS[lang]['weather'].format(
            city=data['name'], temp=round(data['main']['temp']),
            desc=data['weather'][0]['description'].capitalize(), wind=data['wind']['speed']
        )
        await message.answer(text, reply_markup=main_reply_kb(lang))

async def main():
    init_db()
    print("Bot ishga tushdi...")
    await dp.start_polling(bot)
# --- ADMIN PANEL ---
@dp.message(F.text == "/admin", F.from_user.id == ADMIN_ID)
async def admin_menu(message: types.Message):
    kb = [
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Reklama tarqatish", callback_data="admin_broadcast")]
    ]
    await message.answer("Xush kelibsiz, Admin! Kerakli bo'limni tanlang:", 
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "admin_stats", F.from_user.id == ADMIN_ID)
async def show_stats(callback: types.CallbackQuery):
    conn = sqlite3.connect('weather_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    count = cursor.fetchone()[0]
    conn.close()
    await callback.message.answer(f"👥 Botdagi jami foydalanuvchilar: {count} ta")
    await callback.answer()

# Reklama yuborish uchun oddiyroq usul
@dp.callback_query(F.data == "admin_broadcast", F.from_user.id == ADMIN_ID)
async def start_broadcast(callback: types.CallbackQuery):
    await callback.message.answer("Reklama xabarini yuboring (matn ko'rinishida):")
    await callback.answer()

@dp.message(F.from_user.id == ADMIN_ID, F.text)
async def do_broadcast(message: types.Message):
    # Agar xabar /admin bo'lmasa, uni reklama deb hisoblaymiz
    if message.text == "/admin": return

    conn = sqlite3.connect('weather_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    conn.close()

    count = 0
    for user in users:
        try:
            await bot.send_message(user[0], message.text)
            count += 1
            await asyncio.sleep(0.05) # Telegram bloklab qo'ymasligi uchun pauza
        except:
            continue
    
    await message.answer(f"✅ Reklama {count} ta foydalanuvchiga yuborildi!")
    
if __name__ == "__main__":
    asyncio.run(main())
