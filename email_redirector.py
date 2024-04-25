# -*- coding: utf-8 -*-

import email
from email.mime.text        import MIMEText
from email.mime.multipart   import MIMEMultipart
import imaplib
import logging
import smtplib
import time
import yaml


logger = logging.getLogger(__name__)
console = logging.getLogger('console')

config = {}
with open('emailRedirectorConfig.yaml', 'r') as file:
    config = yaml.safe_load(file)

def decode_mime_string(encoded_string):
    decoded_bytes, charset = email.header.decode_header(encoded_string)[0]
    if charset:
        return decoded_bytes.decode(charset)
    else:
        return decoded_bytes

def send_mail(mailObject):

    mailTo  = []
    message = MIMEMultipart("alternative")
    message['From']     = mailObject['From']
    message['To']       = mailObject['To']
    mailTo.append(mailObject['To'])
    mailBcc             = mailObject['Bcc']
    mailTo.extend(mailBcc)
    message['Subject']  = mailObject['Subject']
    message["Cc"]       = ""

    part1 = MIMEText(mailObject["body_txt"], "plain")
    part2 = MIMEText(mailObject["body_html"], "html")
    if mailObject["body_txt"]: message.attach(part1)
    if mailObject["body_html"]: message.attach(part2)
    print ("Sending mail to: " + ', '.join(map(str, mailTo)) + " ...")

    smtpConfig = config['smtp']
    try:
        with smtplib.SMTP_SSL(smtpConfig['host'], smtpConfig['port']) as server:
            server.login(smtpConfig['user'], smtpConfig['pass'])
            server.sendmail(message['From'], mailTo, message.as_string())
            print ("Successfully sent email to " + ', '.join(map(str, mailTo)))
    except smtplib.SMTPException as e:
        print ("Error: unable to send email" + str(e))
    return

def search_and_forward(imap_client):
    status, messages = imap_client.select(mailbox=config['imap']['mailbox'])
    if status != 'OK':
        logger.error('Select inbox failed, message: %s' % messages)
        imap_client.close()
        return


    #In Inbox
    status, mail_ids = imap_client.search(None, 'UNSEEN')
    #status, mail_ids = imap_client.search(None, 'SEEN') # for debug
    if status != 'OK':
        logger.error('Search mail failed, message: %s' % mail_ids)
        imap_client.close()
        return

    if not len(mail_ids[0].decode().split()[-2:]):
        print ("Nothing to do")
        return

    for mail_id in mail_ids[0].decode().split()[-2:]:
        resp_code, mail_data = imap_client.fetch(mail_id, '(RFC822)')
        message = email.message_from_bytes(mail_data[0][1])
        
        mail = {}
        mail['From']    = message.get("From")
        mail['To']      = message.get("To")
        mail['Date']    = message.get("Date")
        mail['Subject'] = message.get("Subject")
        body_plaintext  = ""
        body_html       = ""
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                body_plaintext = part.as_bytes().decode(encoding='UTF-8')
                body_plaintext = body_plaintext.split("\n\n")
                body_plaintext = '\n\n'.join(body_plaintext[1:])
            if part.get_content_type() == "text/html":
                text = f"{part.get_payload(decode=True)}"
                html = text
                body_html = str(html.encode().decode("unicode-escape", errors='ignore').encode('latin-1', errors='ignore').decode('utf-8', errors='ignore')).replace("b'", "")
        mail['body_txt']  = body_plaintext
        mail['body_html'] = body_html


        ###### FILTERS
        mailBcc = []
        for filter in config['filters']:
            if matches_conditions(mail, filter['conditions']):
                print ("Execute filter: " + filter['name'] + " ...")
                for account in config['accountMapping']:
                    if account in mail['To']:
                        actions = filter['actions']
                        for action in actions:
                            mail[action['field']] = action['value']
                        mailBcc.append(mail['DefaultBcc'])
                        mailBcc.extend(config['accountMapping'][account])
                        mail['Bcc']  = mailBcc
                        print ("Mail forwarded to: " + ', '.join(map(str, mailBcc)) + " ...")
                        send_mail(mail)
        ######
    imap_client.close()

def matches_conditions(email, conditions):
    for condition in conditions:
        conditionField = condition['field']
        conditionValue = condition['value']

        # TODO: Add support for operators, fields and conditions
        if conditionValue not in decode_mime_string(email[conditionField]):
            return False

    return True

def run(host, port, ssl, username, password):
    try:
        if ssl:
            imap_client = imaplib.IMAP4_SSL(host=host, port=port)
        else:
            imap_client = imaplib.IMAP4(host=host, port=port)
        typ, message = imap_client.login(username, password)
        if typ != 'OK':
            logger.error('Login failed, message: %s' % message)
            return
        try:
            search_and_forward(imap_client)
        except TimeoutError as e:
            imap_client = None
            logger.error(e)
            console.debug('!')
        except imaplib.IMAP4.abort as e:
            imap_client = None
            logger.debug(e)
            console.info('!')
        except imaplib.IMAP4.error as e:
            imap_client = None
            logger.error(e)
            console.debug('!')
    finally:
        if imap_client is not None:
            imap_client.logout()


def main():
    run(config['imap']['host'], config['imap']['port'], config['imap']['ssl'], config['imap']['user'], config['imap']['pass'])

if __name__ == '__main__':
    main()
