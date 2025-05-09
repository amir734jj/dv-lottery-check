import base64, datetime, io, time, pytz
from os import environ
from threading import Thread
from dotenv import load_dotenv
from flask import Flask, render_template, request, url_for, redirect, send_file, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait
from sqlalchemy import create_engine, Boolean, Column, String, Text, Integer, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from waitress import serve
from pyvirtualdisplay import Display
from PIL import Image, ImageDraw, ImageFont

# Load environment variables
load_dotenv()

SELENIUM_WAIT_SECONDS = 30

display = Display(visible=False, size=(1200, 600))
display.start()

# chrome driver config
chrome_options = Options()
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument('--disable-dev-shm-usage')        

# Selenium CSS selectors
confirmation_elem = (By.CSS_SELECTOR, "#txtCN")
lastname_elem = (By.CSS_SELECTOR, "#txtLastName")
year_elem = (By.CSS_SELECTOR, "#txtYOB")
captcha = (By.CSS_SELECTOR, "#txtCodeInput")
captcha_image = (By.CSS_SELECTOR, "#c_checkstatus_uccaptcha30_CaptchaImage")
submit = (By.CSS_SELECTOR, "#btnCSubmit")
check_status_elem = (By.CSS_SELECTOR, "#maincontent > div:nth-child(3) > div > div > div.panel-body.p5555 > "
                                      "div.col-xs-12.col-sm-12.text-center > div > p:nth-child(2) > a")
continue_elem = (
    By.CSS_SELECTOR, "#main > div:nth-child(2) > div > p.text-center > a")
result_container = (By.CSS_SELECTOR, "#main > div > div > p:nth-child(1)")

# Flask app
app = Flask(__name__, template_folder="templates")

DATABASE_URL = 'sqlite:///db.sqlite'
if environ.get('DATABASE_URL'):
    DATABASE_URL = environ.get('DATABASE_URL')

engine = create_engine(DATABASE_URL)

Base = declarative_base()
Session = sessionmaker(bind=engine)

def add_text_to_image(base64_img, text):
    font = ImageFont.load_default()

    img = Image.open(io.BytesIO(base64.b64decode(base64_img)))

    img_result = ImageDraw.Draw(img)
    img_result.text((100, 210), text, fill=(255, 0, 0), font=font)

    buff = io.BytesIO()
    img.save(buff, format="PNG")
    img_str = base64.encodebytes(buff.getvalue()).decode()

    return img_str


def wait_until(some_predicate, timeout, period=0.25, *args, **kwargs):
    must_end = datetime.datetime.now() + timeout
    while datetime.datetime.now() < must_end:
        if some_predicate(*args, **kwargs):
            return True
        time.sleep(period)
    return False


def clean_captcha(user_id, check_result=True):
    with Session() as session:
        session.query(User) \
            .filter_by(user_id=user_id) \
            .update({'captcha_image': '',
                    "captcha_result": '',
                     "check_result": check_result})
        session.commit()


def check_user_property_is_set(user_id, *props):
    with Session() as session:
        user = session.get(User, user_id)
        return any(map(lambda prop: bool(getattr(user, prop)), props))


def check(user_id):
    with Session() as session:
        user = session.get(User, user_id)
        driver = webdriver.Chrome(options=chrome_options)
        print("current chromedriver session is {}".format(driver.session_id))

        try:
            driver.get("https://dvprogram.state.gov/")

            # Check status disclosure page
            WebDriverWait(driver, SELENIUM_WAIT_SECONDS) \
                .until(expected_conditions.presence_of_element_located(check_status_elem))
            elem = driver.find_element(*check_status_elem)
            elem.click()

            # Welcome page
            WebDriverWait(driver, SELENIUM_WAIT_SECONDS) \
                .until(expected_conditions.presence_of_element_located(continue_elem))
            elem = driver.find_element(*continue_elem)
            elem.click()

            # Form page
            WebDriverWait(driver, SELENIUM_WAIT_SECONDS) \
                .until(expected_conditions.presence_of_element_located(lastname_elem))

            driver.find_element(
                *confirmation_elem).send_keys(user.confirmation_number)
            driver.find_element(*lastname_elem).send_keys(user.lastname)
            driver.find_element(*year_elem).send_keys(user.birth_year)

            captcha_base64 = driver.find_element(*captcha_image).screenshot_as_base64
            
            session.query(User) \
                .filter_by(user_id=user_id) \
                .update({'captcha_image': captcha_base64})
            session.commit()
            
            if not wait_until(lambda: check_user_property_is_set(user_id, "captcha_result"),
                              datetime.timedelta(seconds=60)):
                return False

            WebDriverWait(driver, SELENIUM_WAIT_SECONDS) \
              .until(expected_conditions.presence_of_element_located(submit))

            # Manually captcha result
            driver.find_element(*captcha).send_keys(user.captcha_result)
            
            driver.find_element(*submit).click()

            WebDriverWait(driver, SELENIUM_WAIT_SECONDS) \
              .until(expected_conditions.presence_of_element_located(result_container))

            session.refresh(user)
            screenshot = driver.get_screenshot_as_base64()
            overlay_text = f"{user.lastname} / {user.birth_year} @ {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"

            session.query(User) \
                .filter_by(user_id=user_id) \
                .update({"check_result": driver.find_element(*result_container) is not None,
                        "screenshot": add_text_to_image(screenshot, overlay_text),
                         "last_update": datetime.datetime.now(tz=pytz.utc)})
            session.commit()
        finally:
            clean_captcha(user_id)
            driver.quit()


class User(Base):
    __tablename__ = 'users'
    user_id = Column(Integer, primary_key=True, autoincrement=True)
    lastname = Column(String(100))
    confirmation_number = Column(String(100))
    birth_year = Column(String(100))
    captcha_image = Column(Text())
    captcha_result = Column(String(100))
    check_result = Column(Boolean())
    last_update = Column(DateTime(), default=None)
    screenshot = Column(Text())


@app.route('/')
@app.route('/<int:year>')
def index(year = None):
    with Session() as session:
        users = session.query(User).all()
        years = list(set(map(lambda x: int(x.confirmation_number[:4]), users)))
        
        if year is None:
          year = max(years)
        
        users = session.query(User) \
                       .filter(User.confirmation_number.startswith(year)) \
                       .order_by(User.lastname) \
                       .all()
        return render_template('index.html.jinja', users=users, current_year=year, years=years)

@app.route('/years')
def years():
    with Session() as session:
        users = session.query(User).all()
        
        years = list(set(map(lambda x: int(x.confirmation_number[:4]), users)))
        return jsonify(result=years)

@app.route('/check/<int:user_id>', methods=['GET', 'POST'])
def check_captcha(user_id):
    with Session() as session:
        user = session.get(User, user_id)
        if request.method == 'GET':
            clean_captcha(user_id, check_result=False)

            t = Thread(target=check, args=[user_id])
            t.start()

            if not wait_until(lambda: check_user_property_is_set(user_id, "captcha_image", "captcha_result"),
                              datetime.timedelta(seconds=25)):
                return "Record not found", 400

            session.refresh(user)
            if user.captcha_result:
              return redirect(url_for('index'))
            else:
              return render_template('captcha.html.jinja', user=user)
        else:
            captcha_result = request.form.get('captcha')
            session.query(User) \
                .filter_by(user_id=user_id) \
                .update({'captcha_result': captcha_result})
            session.commit()

            if not wait_until(lambda: check_user_property_is_set(user_id, "check_result"),
                              datetime.timedelta(seconds=60)):
                return "Record not found", 400

            return redirect(url_for('index'))


@app.route('/user/create', methods=['GET', 'POST'])
def create_user():
    if request.method == 'GET':
        return render_template('user.html.jinja')
    else:
        user = User()
        user.lastname = request.form.get('lastname')
        user.birth_year = request.form.get('birth_year')
        user.confirmation_number = request.form.get('confirmation_number')

        with Session() as session:
            session.add(user)
            session.commit()
            return redirect(url_for('index'))


@app.route('/user/screenshot/<int:user_id>', methods=['GET'])
def user_screenshot(user_id):
    with Session() as session:
        user = session.get(User, user_id)
        return send_file(
            io.BytesIO(base64.b64decode(user.screenshot)),
            download_name='screenshot.png',
            mimetype='image/png'
        )

@app.route('/health', methods=['GET'])
def health_check():
    try:
        # Optionally, you can check if the database is accessible or any other service
        with Session() as session:
            # Try to query a simple operation to verify DB connection
            session.query(User).first()
        return jsonify(status="healthy"), 200
    except Exception as e:
        return jsonify(status="unhealthy", error=str(e)), 500

with app.app_context():
    Base.metadata.create_all(bind=engine)
    port = 5000 if environ.get("PORT") is None else int(environ.get("PORT"))
    print("listening to port: %s" % port)
    serve(app, host="0.0.0.0", port=port)
    display.stop()
