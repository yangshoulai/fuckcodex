# 随机人名
import datetime
import random
import string
from typing import List

from service.base_mail_service import MailBox

FIRST_NAMES = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas", "Charles",
    "Christopher", "Daniel", "Matthew", "Andrew", "Steven", "Mark", "Paul", "George", "Kenneth", "Edward",
    "Jason", "Brian", "Kevin", "Ronald", "Timothy", "Jeffrey", "Ryan", "Jacob", "Gary", "Nicholas",
    "Eric", "Jonathan", "Stephen", "Larry", "Justin", "Scott", "Brandon", "Benjamin", "Samuel", "Gregory",
    "Alexander", "Patrick", "Dennis", "Jerry", "Tyler", "Aaron", "Jose", "Adam", "Nathan", "Henry",
    "Zachary", "Jeremy", "Ethan", "Austin", "Jesse", "Christian", "Alan", "Shane", "Peter", "Douglas",
    "Keith", "Gerald", "Lawrence", "Roger", "Terry", "Sean", "Caleb", "Logan", "Dylan", "Blake",
    "Noah", "Liam", "Mason", "Elijah", "Oliver", "Lucas", "Aiden", "Eli", "Miles", "Calvin",
    "Jordan", "Colin", "Spencer", "Travis", "Isaac", "Gavin", "Adrian", "Xavier", "Jared", "Grant"
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
    "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
    "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell", "Carter", "Roberts",
    "Turner", "Parker", "Evans", "Edwards", "Collins", "Stewart", "Morris", "Rogers", "Reed", "Cook",
    "Morgan", "Bell", "Murphy", "Bailey", "Cooper", "Howard", "Ward", "Brooks", "Hughes", "Gray",
    "James", "Reyes", "Cruz", "Diaz", "Richardson", "Wood", "Watson", "Bennett", "Henderson", "Coleman",
    "Jenkins", "Perry", "Powell", "Long", "Patterson", "Harrison", "Ross", "Foster", "Graham", "Sullivan"
]


def _generate_username():
    """生成随机用户名"""
    return random.choice(FIRST_NAMES), random.choice(LAST_NAMES)


def _generate_password(length: int = 12) -> str:
    """生成密码（至少包含大小写字母）"""
    length = length if length > 12 else 12
    upper = random.choice(string.ascii_uppercase)
    lower = random.choice(string.ascii_lowercase)
    rest_len = length - 2
    rest = random.choices(string.ascii_letters + string.digits, k=rest_len)
    password_list = [upper, lower] + rest
    random.shuffle(password_list)
    return "".join(password_list)


def _generate_birthdate(start="2001-01-01", end="2004-12-31"):
    s = datetime.datetime.strptime(start, "%Y-%m-%d")
    e = datetime.datetime.strptime(end, "%Y-%m-%d")
    d = random.randint(0, (e - s).days)
    return (s + datetime.timedelta(days=d)).strftime("%Y-%m-%d")


class Account:
    first_name: str
    last_name: str
    username: str
    password: str
    birthday: List[str]
    email: str
    mail_box: MailBox
    mobile: str




def create_new_account(mail_box: MailBox, password_length: int = 12) -> Account:
    first_name, last_name = _generate_username()
    password = _generate_password(password_length)
    birthdate = _generate_birthdate()
    account = Account()
    account.first_name = first_name
    account.last_name = last_name
    account.username = f"{first_name} {last_name}"
    account.birthday = birthdate.split("-")
    account.password = password
    account.email = mail_box.email
    account.mail_box = mail_box
    return account
