#!/usr/bin/env python
'''
webdipnotify.py

This script is intended to be run from the command line once to fill out the
config values, and then put into a personal crontab.

I recommend not running it more than once per hour to reduce demand on the
webdiplomacy server.

If the script cannot find the sqlite file, it will create a new one.

Many things are currently hardcoded. I'm waiting to see which ones need to
change.

'''

import urllib
import urllib2
import sqlite3
import os.path
from pyquery import PyQuery
import smtplib
from email.mime.text import MIMEText

HOME_URL = 'http://webdiplomacy.net/index.php'
WEB_DIP_DB_FILE = os.path.expanduser('~/.webdiplomacy.db')

def credentials_table_exists(curs):
    '''
    test for the existence of the credentials table
    '''
    try:
        curs.execute('select 1 from credentials')
        curs.fetchall()
        return True
    except sqlite3.OperationalError:
        return False

def create_credentials_table(curs):
    '''
    if the credentials table doesn't exist, create it
    '''
    curs.execute('''create table credentials (
        id int primary key not null check (id = 1), loginuser, loginpass,
        smtp_server, smtp_port, smtp_from, smtp_to, smtp_user, smtp_password
        )''')

def boards_table_exists(curs):
    '''
    test for the existence of the boards table
    '''
    try:
        curs.execute('select 1 from boards')
        curs.fetchall()
        return True
    except sqlite3.OperationalError:
        return False

def create_boards_table(curs):
    '''
    if the boards table doesn't exist, create it
    '''
    curs.execute('''create table boards ( id int primary key, name,
        my_country, date, phase, order_status, has_mail) ''')

def fetch_credentials(curs):
    '''
    fetch credentials from the database
    '''
    curs.execute('select * from credentials where id = 1')
    return curs.fetchone()

def create_credentials(curs):
    '''
    get credentials from the user and put them in the database
    '''
    creds = {}
    creds['loginuser'] = raw_input('username: ')
    creds['loginpass'] = raw_input('password: ')
    creds['smtp_server'] = raw_input('smtp server name: ')
    creds['smtp_port'] = raw_input('smtp port (usually 587): ')
    creds['smtp_from'] = raw_input('who should this email be from: ')
    creds['smtp_to'] = raw_input('who is this email to: ')
    creds['smtp_user'] = raw_input('smtp user name: ')
    creds['smtp_password'] = raw_input('smtp password: ')
    curs.execute('''insert into credentials (id, loginuser, loginpass,
        smtp_server, smtp_port, smtp_from, smtp_to, smtp_user, smtp_password)
        values (1, :loginuser, :loginpass, :smtp_server, :smtp_port,
        :smtp_from, :smtp_to, :smtp_user, :smtp_password)''',
        creds)
    curs.connection.commit()
    return creds

def fetch_web_response(creds):
    '''
    fetch web page using form
    '''
    post_values = {'loginuser': creds['loginuser'],
                    'loginpass': creds['loginpass']}

    data = urllib.urlencode(post_values)
    req = urllib2.Request(HOME_URL, data)
    return urllib2.urlopen(req)

def save_new_board(curs, board):
    '''
    save a new board
    '''
    curs.execute('''insert into boards(id, name, my_country, phase, date,
        order_status,has_mail) values (:id, :name, :my_country, :phase, :date,
        :order_status, :has_mail)''', board)

    curs.connection.commit()

def update_existing_board(curs, board):
    '''
    update an existing board
    '''
    curs.execute('''update boards set phase = :phase, date = :date,
        order_status = :order_status, has_mail = :has_mail where id = :id''',
        board)

    curs.connection.commit()

def extract_game(panel):
    '''
    given a pyquery doc specific to the game panel, extract the relevant game
    information
    '''
    found_game = {}
    found_game['id'] = panel('.homeGameTitleBar').attr('gameid')
    found_game['name'] = panel('.homeGameTitleBar').text()
    found_game['my_country'] = panel('.memberYourCountry').eq(0).text()
    found_game['phase'] = panel('.gamePhase').text()
    found_game['date'] = panel('.gameDate').text()
    found_game['time_remaining'] = panel('.timeremaining').text()
    found_game['order_status'] = 'No Orders Due This Phase'
    found_game['has_mail'] = 0
    # loop through all images, find the unread mail icon, if any.
    # any other icon is order status
    for i in panel('.memberUserDetail').find('img'):
        alt_text = i.attrib['alt']
        if alt_text == 'Unread message':
            found_game['has_mail'] = 1
        else:
            found_game['order_status'] = alt_text

    return found_game

def fetch_existing_game(curs, game):
    '''
    fetch whatever we already knew about this game (if anything)
    '''
    curs.execute('select * from boards where id = :id', game)
    return curs.fetchone()

def send_alert(creds):
    '''
    actually deliver the alert
    '''
    msg = MIMEText('check webdiplomacy, something happened')
    msg['Subject'] = 'webdiplomacy alert'
    msg['From'] = creds['smtp_from']
    msg['To'] = creds['smtp_to']
    mailer = smtplib.SMTP(creds['smtp_server'], int(creds['smtp_port']))
    mailer.ehlo()
    mailer.starttls()
    mailer.ehlo()
    mailer.login(creds['smtp_user'], creds['smtp_password'])
    mailer.sendmail(msg['From'], msg['To'], msg.as_string())


def main():
    '''
    starting point
    '''
    conn = sqlite3.connect(WEB_DIP_DB_FILE)
    conn.row_factory = sqlite3.Row
    curs = conn.cursor()

    if not credentials_table_exists(curs):
        create_credentials_table(curs)

    if not boards_table_exists(curs):
        create_boards_table(curs)

    creds = fetch_credentials(curs) or create_credentials(curs)

    response = fetch_web_response(creds)

    alert = False

    doc = PyQuery(response.read())
    for game_panel in doc('.gamePanelHome').items():
        found_game = extract_game(game_panel)
        existing_game = fetch_existing_game(curs, found_game)
        if not existing_game:
            save_new_board(curs, found_game)
            alert = True
        else:
            update_existing_board(curs, found_game)

            if found_game['date'] != existing_game['date']:
                # date changed
                alert = True
            elif found_game['phase'] != existing_game['phase']:
                # phase changed
                alert = True
            elif found_game['has_mail'] == 1 and existing_game['has_mail'] == 0:
                # new mail
                alert = True

    if alert:
        send_alert(creds)

if __name__ == '__main__':
    main()

