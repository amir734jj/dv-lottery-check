import base64
import datetime
import io
import time
from os import environ
from threading import Thread

from flask import Flask, render_template, request, url_for, redirect, send_file
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait
from sqlalchemy import create_engine, Boolean, Column, String, Text, Integer, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from waitress import serve
from pyvirtualdisplay import Display

SELENIUM_WAIT_SECONDS = 10

display = Display(visible=False, size=(1200, 600))
display.start()

# chromedriver config
chrome_options = Options()
chrome_options.add_argument("--no-sandbox")

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

# Flask app
app = Flask(__name__, template_folder="templates")

DATABASE_URL = 'sqlite:///db.sqlite'
if environ.get('DATABASE_URL') is not None:
    DATABASE_URL = environ.get('DATABASE_URL')

engine = create_engine(DATABASE_URL)

Base = declarative_base()
Session = sessionmaker(bind=engine)


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


def check_user_property_is_set(user_id, prop):
    with Session() as session:
        user = session.get(User, user_id)
        return bool(getattr(user, prop))


def check(user_id):
    with Session() as session:
        user = session.get(User, user_id)

        driver = webdriver.Chrome(options=chrome_options)
        try:
            driver.get("https://dvprogram.state.gov/")

            WebDriverWait(driver, SELENIUM_WAIT_SECONDS) \
                .until(expected_conditions.presence_of_element_located(check_status_elem))
            elem = driver.find_element(*check_status_elem)
            elem.click()

            WebDriverWait(driver, SELENIUM_WAIT_SECONDS) \
                .until(expected_conditions.presence_of_element_located(continue_elem))
            elem = driver.find_element(*continue_elem)
            elem.click()

            WebDriverWait(driver, SELENIUM_WAIT_SECONDS) \
                .until(expected_conditions.presence_of_element_located(lastname_elem))

            driver.find_element(
                *confirmation_elem).send_keys(user.confirmation_number)
            driver.find_element(*lastname_elem).send_keys(user.lastname)
            driver.find_element(*year_elem).send_keys(user.birth_year)

            session.query(User) \
                .filter_by(user_id=user_id) \
                .update({'captcha_image': driver.find_element(*captcha_image).screenshot_as_base64})
            session.commit()

            if not wait_until(lambda: check_user_property_is_set(user_id, "captcha_result"),
                              datetime.timedelta(seconds=60)):
                return False

            session.refresh(user)
            driver.find_element(*captcha).send_keys(user.captcha_result)
            driver.find_element(*submit).click()
            screenshot = driver.get_screenshot_as_base64()

            session.query(User) \
                .filter_by(user_id=user_id) \
                .update({"check_result": True,
                        "screenshot": screenshot,
                         "last_update": datetime.datetime.utcnow()})
            session.commit()
        finally:
            clean_captcha(user_id)
            driver.close()


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
def index():
    with Session() as session:
        return render_template('index.html.jinja', users=session.query(User).all())


@app.route('/check/<int:user_id>', methods=['GET', 'POST'])
def check_captcha(user_id):
    with Session() as session:
        user = session.get(User, user_id)
        if request.method == 'GET':
            clean_captcha(user_id, check_result=False)

            t = Thread(target=check, args=[user_id])
            t.start()

            if not wait_until(lambda: check_user_property_is_set(user_id, "captcha_image"),
                              datetime.timedelta(seconds=15)):
                return "Record not found", 400

            session.refresh(user)
            return render_template('captcha.html.jinja', user=user)
        else:
            captcha_result = request.form.get('captcha')
            session.query(User) \
                .filter_by(user_id=user_id) \
                .update({'captcha_result': captcha_result})
            session.commit()

            if not wait_until(lambda: check_user_property_is_set(user_id, "check_result"),
                              datetime.timedelta(seconds=5)):
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
        return send_file(
            io.BytesIO(base64.b64decode(
                session.get(User, user_id).screenshot)),
            download_name='screenshot.png',
            mimetype='image/png'
        )


with app.app_context():
    Base.metadata.create_all(bind=engine)
    port = 5000 if environ.get("PORT") is None else int(environ.get("PORT"))
    print("listening to port: %s" % port)
    serve(app, host="0.0.0.0", port=port)
    display.stop()
