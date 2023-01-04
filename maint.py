#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import sys

import threading

sys.path.append('./venv/lib/python3.9/site-packages')

import mastodon_listener
from mysql_store import MessageStore
from sqlite_store import MessageStore as SqliteStore
from queue import Empty, Queue
from mastodon_listener import MastodonUser
# import command_parser
import re
import gxmpp
import json
import db
from time import time, sleep
import datetime

import config

SERVICE_NAME = config.SERVICE_NAME
HOSTNAME = config.HOSTNAME
HOST = SERVICE_NAME + '.' + HOSTNAME
xmpp_jid = HOST
USERS_DB = config.USERS_DB
MESSAGES_DB = config.MESSAGES_DB
xmpp_password = config.XMPP_PASSWORD
xmpp_server = config.XMPP_SERVER
xmpp_port = config.XMPP_PORT
xmpp_queue = 0

try:
    MYSQL_HOST = config.MYSQL_HOST
    MYSQL_PORT = config.MYSQL_PORT
    MYSQL_DATABASE = config.MYSQL_DATABASE
    MYSQL_USERNAME = config.MYSQL_USERNAME
    MYSQL_PASSWORD = config.MYSQL_PASSWORD
    USE_MYSQL = config.USE_MYSQL
except AttributeError:
    MYSQL_HOST = None
    MYSQL_PORT = None
    MYSQL_DATABASE = None
    MYSQL_USERNAME = None
    MYSQL_PASSWORD = None
    USE_MYSQL = False

ADMIN_JID = config.ADMIN_JID

notification_queue = Queue()
update_queue = Queue()
xmpp2m_queue = Queue()
last_timeout_check_time=0
mastodon_listeners = {}

TEST_MODE=0
XMPP = 0
RUN = 1
# MTHREADS=[]

def getMessageStore():
    if USE_MYSQL:
        return MessageStore(MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USERNAME, MYSQL_PASSWORD)
    else:
        return SqliteStore(MESSAGES_DB)

def get_uniq_mids(users: list) -> dict:
    mu = {}
    for u in users:
        if not mu.get(u['mid']):
            mu[u['mid']] = {}
            mu[u['mid']]['jids'] = list([u['jid']])
            mu[u['mid']]['token'] = u['token']
            mu[u['mid']]['receive_replies'] = u['receive_replies']
        else:
            mu[u['mid']]['jids'].append(u['jid'])
    return mu


def get_mentions(thread: list) -> str:
    mentions = set()
    for m in thread:
        mentions.update(m.mentions)
    return " ".join(mentions)


async def process_update(event):
    try:
        asyncio.current_task().set_name('process_update')
    except Exception as e:
        print(e)
    while RUN:
        try:
            # print("pu")
            message = update_queue.get(block=False)
            print(datetime.datetime.now().astimezone().replace(microsecond=0).isoformat())
            print("update queue is not empty")
            _m = message['status']
            print("mid:", message['mid'])
            print(_m.mentions)
            print("mentions:", _m.mentions)
            print("from:", _m.from_mid)
            print("mid:", message['mid'])
            if _m.in_reply_to_id:
                print("reply to", _m.in_reply_to_id)
                if '@' + message['mid'] in _m.mentions:
                    print ("Undo update. We will receive it via notification")
                    continue
                if _m.from_mid != '@' + message['mid']: # not our own message
                    t = threading.Thread(target=_mastodon_process_reply_process, args=(message['mid'], _m.id, _m))
                    t.start()
                else:
                    print("Got own message. Ignoring")
            else:
                print("passed to xmpp")
                for j in message['m'].jids:
                    msg = XMPP.make_message(j,
                                            _m.text,
                                            mfrom='home@' + HOST,
                                            mtype='chat')
                    msg.send()
                    message_store.add_message(
                        _m.text,
                        _m.url,
                        _m.from_mid,
                        _m.mentions,
                        _m.visibility,
                        _m.id,
                        message['mid'],
                        _m.date
                    )
                # autobost processing
                try:
                    print("autoboost processing")
                    for j in message['m'].jids:
                        print("for " + str(j))
                        l = users_db.getAutoboostByJid(j)
                        print("autoboost names:\n" + str(l))
                        print("post from " + str(_m.from_mid))
                        if _m.from_mid.lower() in l:
                            print("got reblog")
                            mastodon = mastodon_listeners.get(message['mid'])
                            if mastodon:
                                mastodon.status_reblog(_m.id)
                except Exception as e:
                    print(str(e))
        except Empty:
            await asyncio.sleep(0.2)
            # pass
        except Exception as e:
            print("Exception: \n" + srt(e))
        except:
            print("unhandled exception")
        # print('.', end='')
    print(asyncio.current_task().get_name(),
        'is closed')


async def process_notification(event):
    try:
        asyncio.current_task().set_name('process_notification')
    except Exception as e:
        print(e)
    # asyncio.current_task().set_name('process_notofication')
    while RUN:
        try:
            # print("pn")
            message = notification_queue.get(block=False)
            print(message)
            _m = message['status']
            print("\n\n====")
            print(_m.to_dict())
            print("====\n\n\n")
            if _m.type == 'mention':
                ok = 1
                if _m.in_reply_to_id:
                    print("reply to id:", _m.in_reply_to_id)
                    t = threading.Thread(target=_mastodon_process_reply_process, args=(message['mid'], _m.id, _m, 'notification'))
                    t.start()
                    print("process started")
                else:
                    print("Not reply")
                    try:
                        message_store.add_message(
                            _m.text,
                            _m.url,
                            _m.from_mid,
                            _m.mentions,
                            _m.visibility,
                            _m.id,
                            message['mid'],
                            _m.date,
                            _m.id
                        )
                        for j in message['m'].jids:
                            msg = XMPP.make_message(
                                j,
                                _m.text,
                                mtype='chat',
                                mfrom=str(_m.id) + "@" + HOST)
                            msg.send()
                    except Exception as e:
                        print("Error: " + str(e))
            # elif _m.type=='favourite' or _m.type=='reblog':
            #     message_store.add_message(
            #                 _m.text,
            #                 _m.url,
            #                 '',
            #                 _m.visibility,
            #                 _m.id,
            #                 message['mid']
            #             )
            #     for j in message['m'].jids:
            #         msg = XMPP.make_message(
            #             j,
            #             _m.text,
            #             mtype='chat',
            #             mfrom='home@'+HOST)
            #         msg.send()
            else:
                for j in message['m'].jids:
                    msg = XMPP.make_message(
                        j,
                        _m.text,
                        mtype='chat',
                        mfrom='home@' + HOST)
                    msg.send()
        except Empty:
            await asyncio.sleep(.2)
            # pass
        except Exception as e:
            print("Exception", e)
        # print('process_notification')
    print(asyncio.current_task().get_name(),
        'is closed')


def process_xmpp_home(message):
    print("process_xmpp_home")
    user = users_db.get_user_by_jid(message['jid'])
    if not user:
        print("user not found")
        return
    mastodon = mastodon_listeners.get(user['mid'])
    if not mastodon:
        print("not mastodon")
        msg = XMPP.make_message(
            message['jid'],
            'Seems like you have not registered or internal exception accured'
            ,
            mfrom='home@' + HOST,
            mtype='chat')
        msg.send()
        return
    body = message['body']
    if re.match(r'h(elp)?$', body, re.I | re.MULTILINE):
        help_message = '''HELP
. - open last message in separate chat dialog
.1 - open next-to-last message in separate chat dialog
.2 - open 3-rd to-last message ...
and so on up to 99-th message

r - reblog last message
r1 - reblog next-to-last message
r2 - reblog 3-rd to-last message
and so on up to 99-th message

f - favourite last message
f1 - favourite next-to-last message
f2 - favourite 3-rd to-last message
and so on up to 99-th message


w - get link to last message
w1 - get link to next-to-last message
and so on up to 99-th message

Also you can use quotation to point desired message.
For example:
    > @someuser@mastodon:
    > nice weather, isn't it?
    .
will open message with such text in separate chat dialog

h - this help

Notes!
You cannot answer to massages from this chat directly. To answer to message please open it on separate chat dialog
You cannot write new messages in this chat. To make new massage please send it to new@{0} contact
'''.format(HOST)
        print("help")
        msg = XMPP.make_message(
            message['jid'],
            help_message,
            mtype='chat',
            mfrom='home@' + HOST)
        msg.send()
    elif re.match(r'\.(\d{1,2})?$', body, re.I | re.MULTILINE):
        res = re.findall(r'^\.(\d+)', body)
        h_id = 0
        if res:
            h_id = int(res[0])
        print("Going to get message", h_id)
        ms = message_store.get_messages_for_user(user['mid'])
        if h_id >= len(ms):
            raise mastodon_listener.NotFoundError()
        mes_x = ms[h_id]
        print("Got message! mid=", mes_x)
        t = threading.Thread(target=mastodon_get_thread_process, args=(message['jid'],mes_x), name='mastodon_getthread_'+message['jid'])
        t.start()
        # MTHREADS.append(t)
    elif re.match(r'r(\d{1,2})?$', body, re.I | re.MULTILINE):
        res = re.findall(r'^r(\d+)', body, re.I)
        h_id = 0
        if res:
            h_id = int(res[0])
        print("Going to get message", h_id)
        ms = message_store.get_messages_for_user(user['mid'])
        if h_id >= len(ms):
            raise mastodon_listener.NotFoundError()
        mes_x = ms[h_id]
        t = threading.Thread(target=mastodon_reblog_fav_status_process, args=('r', message['jid'],mes_x), name='mastodon_reblog_'+message['jid'])
        t.start()
        # MTHREADS.append(t)
    elif re.match(r'f(\d{1,2})?$', body, re.I | re.MULTILINE):
        res = re.findall(r'^f(\d+)', body, re.I)
        h_id = 0
        if res:
            h_id = int(res[0])
        print("Going to get message", h_id)
        ms = message_store.get_messages_for_user(user['mid'])
        if h_id >= len(ms):
            raise mastodon_listener.NotFoundError()
        mes_x = ms[h_id]
        t = threading.Thread(target=mastodon_reblog_fav_status_process, args=('f', message['jid'],mes_x), name='mastodon_reblog_'+message['jid'])
        t.start()
        # MTHREADS.append(t)
    elif re.match(r'w(\d{1,2})?$', body, re.I | re.MULTILINE):
        res = re.findall(r'^w(\d+)', body, re.I)
        h_id = 0
        if res:
            h_id = int(res[0])
        print("Going to get link to message", h_id)
        ms = message_store.get_messages_for_user(user['mid'])
        if h_id >= len(ms):
            raise mastodon_listener.NotFoundError()
        mes_x = message_store.get_message_by_id(ms[h_id])
        if mes_x:
            msg = XMPP.make_message(
                message['jid'],
                mes_x['url'],
                mtype='chat',
                mfrom='home@' + HOST)
            msg.send()
    elif re.match(r'(?:>|»)', body, re.I | re.MULTILINE):
        print("quotation")
        strings = body.split('\n')
        print(strings)
        original_post = ''
        while len(strings) > 0:
            l = strings.pop(0)
            q = re.search(r'(?:>|») ?(.+)', l)
            if q and q.group(1):
                original_post += q.group(1) + '\n'
            else:
                strings.append(l)  # return a string back
                break  # end of quotation
        print('Original post was:')
        original_post = original_post.rstrip()
        print(original_post)
        toot = message_store.find_message(original_post, user['mid'])
        if not toot:
            raise mastodon_listener.NotFoundError()
        message_id = toot['id']
        command = "\n".join(strings)
        print("command:" + command)
        print("message id:" + message_id)
        if command == '.' or command == '':  # get thread
            t = threading.Thread(target=mastodon_get_thread_process, args=(message['jid'],message_id), name='mastodon_getthread_'+message['jid'])
            t.start()
            # MTHREADS.append(t)
        elif command.lower() == 'r':  # reblog status
            t = threading.Thread(target=mastodon_reblog_fav_status_process, args=('r', message['jid'],message_id), name='mastodon_reblog_'+message['jid'])
            t.start()
            # MTHREADS.append(t)
        elif command.lower() == 'f':  # favourite status
            t = threading.Thread(target=mastodon_reblog_fav_status_process, args=('f', message['jid'],message_id), name='mastodon_reblog_'+message['jid'])
            t.start()
            # MTHREADS.append(t)
        elif command.lower() == 'w':  # get link
            msg = XMPP.make_message(
                message['jid'],
                toot['url'],
                mtype='chat',
                mfrom='home@' + HOST)
            msg.send()
    else:
        msg = XMPP.make_message(
            message['jid'],
            'Unknown command\n' +
            'If you want to write new post then please send your message to contact new@{0}'.format(HOST),
            mtype='chat',
            mfrom='home@' + HOST)
        msg.send()


def process_xmpp_new(message):
    user = users_db.get_user_by_jid(message['jid'])
    if not user:
        return
    mastodon = mastodon_listeners.get(user['mid'])
    if not mastodon:
        return
    body = message['body']
    t = threading.Thread(
        target=mastodon_post_status_process, args=(
            message['jid'],
            0, # in_reply_to_id
            body,
            'public' #visibility
            ),
        name='mastodon_post_'+message['jid']
        )
    t.start()
    # MTHREADS.append(t)

def process_xmpp_thread(message):
    user = users_db.get_user_by_jid(message['jid'])
    if not user:
        return
    mastodon = mastodon_listeners.get(user['mid'])
    if not mastodon:
        return
    mid = re.findall(r'(\d+)@', message['to'])[0]
    print(mid)
    body = message['body']
    if body == '.':
        print("get thread")
        t = threading.Thread(target=mastodon_get_thread_process, args=(message['jid'],mid), name='mastodon_getthread_'+message['jid'])
        t.start()
        # MTHREADS.append(t)
    elif body.upper() == 'W':  # Get link
        message_store = getMessageStore()
        # TODO: change dict to EncodedMessage type
        toot = message_store.get_message_by_id(mid)
        if not toot:
            print("no toot in message store. Getting from mastodon...")
            toot = mastodon.get_status(mid)
            if not toot:
                raise mastodon_listener.NotFoundError
        try:
            print(type(toot))
            if type(toot) == dict:
                msg = XMPP.make_message(
                    message['jid'],
                    toot['url'],
                    mfrom=str(mid) + '@' + HOST,
                    mtype='chat')
            else:
                msg = XMPP.make_message(
                    message['jid'],
                    toot.url,
                    mfrom=str(mid) + '@' + HOST,
                    mtype='chat')
            msg.send()
        except:
            e = sys.exc_info()[0]
            print(str(e))
            msg = XMPP.make_message(
                message['jid'],
                "Internal error. Sorry. :-(",
                mfrom=str(mid) + '@' + HOST,
                mtype='chat')
            msg.send()
    elif body.upper() == 'RR':  # Reblog first message
        # toot=message_store.get_message_by_id(mid)
        # if not toot:
            # toot=mastodon.get_status(mid)
        t = threading.Thread(target=mastodon_reblog_fav_status_process, args=('r', message['jid'],mid), name='mastodon_reblog_'+message['jid'])
        t.start()
        # MTHREADS.append(t)
        # in some cases we do not have last message in our base. For example if we get thread by .
    # elif body.upper() == 'R': #Reblog last message
    #     t=message_store.get_messages_for_user_by_thread(user['mid'],mid)
    #     _m=mastodon.status_reblog(t.get(0))
    #     if _m:
    #         msg = XMPP.make_message(
    #             message['jid'],
    #             _m.text,
    #             mtype='chat',
    #             mfrom='home@'+HOST)
    #         msg.send()
    elif body.upper() == 'M':
        message_store = getMessageStore()
        messages = message_store.get_messages_for_user_by_thread(
            user['mid'],
            mid
        )
        print(messages)
        message_id = messages[0]
        answer = body
        last_message = message_store.get_message_by_id(message_id)
        mentions = last_message['mentions'].lower().split(' ')
        mentions_str = '\n'.join(mentions)
        mentions_str = "All mentions:\n" + mentions_str
        mentions_str.rstrip();
        msg = XMPP.make_message(
                        message['jid'],
                        mentions_str,
                        mtype='chat',
                        mfrom=str(mid) + '@' + HOST)
        msg.send()
    elif body.upper() == 'H':  # Get help
        msg = XMPP.make_message(
            message['jid'],
            'HELP\n' +
            'w - get link\n' +
            '. - get full thread\n' +
            'm - get list of mentions\n' +
            # 'r - reblog LAST received message in thread\n'+
            'rr - reblog FIRST message in thread\n' +
            'h - this help\n' +
            'text - post answer\n\n'
            '> quotation\n' +
            'text\n' +
            'Post answer to desired status\n\n' +
            '> quotation\n' +
            'f\n' +
            'favourite quoted post\n' +
            '> quotation\n' +
            'r\n' +
            'reblog quoted post\n'
            ,
            mfrom=str(mid) + '@' + HOST,
            mtype='chat')
        msg.send()
    else:
        if len(body) > 2:  # Answer to post
            message_id = 0
            message_store = getMessageStore()
            if re.match(r'(?:>|»)', body, re.I | re.MULTILINE):  # quotation
                print("quotation in thread")
                strings = body.split('\n')
                print(strings)
                original_post = ''
                while len(strings) > 0:
                    l = strings.pop(0)
                    q = re.search(r'(?:>|») ?(.+)', l)
                    if q and q.group(1):
                        original_post += q.group(1) + '\n'
                    else:
                        strings.insert(0,l)  # return a string back
                        break  # end of quotation
                print('Original post was:')
                original_post=original_post.rstrip()
                print('"'+original_post+'"')
                toot = message_store.find_message(original_post, user['mid'], feed=mid)
                if not toot:
                    raise mastodon_listener.NotFoundError()
                message_id = toot['id']
                answer = "\n".join(strings)

            # toot=message_store.get_message_by_id(mid)
            try:  # Answer to last received message in the thread
                if not message_id:
                    messages = message_store.get_messages_for_user_by_thread(
                        user['mid'],
                        mid
                    )
                    print(messages)
                    message_id = messages[0]
                    answer = body
                print("original message_id", message_id)
                last_message = message_store.get_message_by_id(message_id)
                print(last_message)
                mentions = last_message['mentions'].lower().split(' ')
                author = ''
                try:
                    author = mentions.pop(0)
                    while mentions.count(author):
                        mentions.remove(author)
                    while mentions.count('@' + user['mid'].lower()):
                        mentions.remove('@' + user['mid'].lower())
                    if author == '@' + user['mid'].lower():
                        author = ''
                except ValueError:
                    pass
                if len(answer) > 2:
                    #mentions.append(author)
                    mentions_str = (' '.join(mentions)).strip()
                    print("Answer from " + user['mid'])
                    print("Mentions: '" + mentions_str + "'")
                    if author:
                        answer = author + ' ' + answer
                    if mentions_str:
                        answer = answer + '\n' + mentions_str
                    t = threading.Thread(
                        target=mastodon_post_status_process, args=(
                            message['jid'],
                            message_id, # in_reply_to_id
                            answer,
                            last_message['visibility']
                            ),
                        name='mastodon_reblog_'+message['jid']
                        )
                    t.start()
                    # MTHREADS.append(t)
                else:
                    if answer.upper() == 'W':
                        msg = XMPP.make_message(
                                        message['jid'],
                                        toot['url'],
                                        mtype='chat',
                                        mfrom=str(mid) + '@' + HOST)
                        msg.send()
                    elif answer.lower() == 'r':  # reblog status
                        t = threading.Thread(target=mastodon_reblog_fav_status_process, args=('r', message['jid'],message_id), name='mastodon_reblog_'+message['jid'])
                        t.start()
                        # MTHREADS.append(t)
                    elif answer.lower() == 'f':  # favourite status
                        t = threading.Thread(target=mastodon_reblog_fav_status_process, args=('f', message['jid'],message_id), name='mastodon_favourite_'+message['jid'])
                        t.start()
                        # MTHREADS.append(t)
                    else:
                        print('answer too short')
                        msg = XMPP.make_message(
                            message['jid'],
                            'answer too short, it should be more than 2 chars',
                            mfrom=str(mid) + '@' + HOST,
                            mtype='chat')
                        msg.send()
                # thread=mastodon.get_thread(mid)
                # mentions_str=get_mentions(thread)
                # mastodon.status_post(
                #     status=mentions_str + ' ' + body,
                #     in_reply_to_id=thread[-1].id,
                #     visibility=thread[-1].visibility
                # )
                # message_store.update_mentions(
                #     mid,
                #     ['@'+user.get('mid')]
                # )
            except mastodon_listener.APIError as e:
                msg = XMPP.make_message(
                    message['jid'],
                    str(e),
                    mfrom=str(mid) + '@' + HOST,
                    mtype='chat')
                msg.send()
            except Exception as e:
                msg = XMPP.make_message(
                    message['jid'],
                    'Internal error',
                    mfrom=str(mid) + '@' + HOST,
                    mtype='chat')
                msg.send()
                msg = XMPP.make_message(
                    ADMIN_JID,
                    str(e) + "\n" +
                    "message_id" + str(mid) + "\n" +
                    "for " + message['jid'],
                    mfrom='alerts@' + HOST,
                    mtype='chat')
                msg.send()
        else:  # seems like an error in command input
            msg = XMPP.make_message(
                message['jid'],
                'Unknown command\n' +
                'w - get link\n' +
                '. - get full thread\n' +
                'm - get list of mentions\n' +
                # 'r - reblog LAST received message in thread\n'+
                'rr - reblog FIRST message in thread\n' +
                'h - this help\n' +
                'text - post answer\n\n'
                '> quotation\n' +
                'text\n' +
                'Post answer to desired status\n\n' +
                '> quotation\n' +
                'f\n' +
                'favourite quoted post\n'
                ,
                mfrom=str(mid) + '@' + HOST,
                mtype='chat')
            msg.send()


def process_xmpp_config(message):
    user = users_db.get_user_by_jid(message['jid'])
    body = message['body']
    if not user:
        body = body.lower()
        if body.startswith('server '):
            server = re.sub(r'server\W+', '', body)
            t = threading.Thread(target=mastodon_register_process, args=(server,message['jid']), name='mastodon_'+server)
            t.start()
            # MTHREADS.append(t)
                
        else:
            msg = XMPP.make_message(
                message['jid'],
                'You are not registered, please assign your mastodon server (for example mastodon.social) with "server" command\n' +
                'server mastodon.social',
                mfrom='config@' + HOST,
                mtype='chat')
            msg.send()
        return
    else:
        if user['status'] == 'registration':
            if body.startswith('server ') or not mastodon_listeners.get(message['jid']):
                users_db.del_user_by_jid(message['jid'])
                process_xmpp_config(message)
                return
            code = body
            print("User in registration")
            m = mastodon_listeners.get(message['jid'])
            print("checking token with server", user['mid'])
            t = threading.Thread(target=mastodon_register_finish_process, args=(message['jid'],code), name='mastodon_'+message['jid'])
            t.start()
            # MTHREADS.append(t)
            
        else:
            body = body.lower()
            if body.startswith('server '):
                try:
                    mastodon = mastodon_listeners.get(user['mid'])
                    users_db.del_user_by_jid(message['jid'])
                    mastodon.jids.remove(message['jid'])
                    if len(mastodon.jids) < 1:
                        print("closing stream")
                        mastodon.close_listener()
                        mastodon_listeners.pop(user['mid'])
                except (KeyError, AttributeError) as e:
                    print("Error deleting listener:", str(e))
                    # pass
                process_xmpp_config(message)
            elif body == 'help':
                msg = XMPP.make_message(
                    message['jid'],
                    'HELP\n' +
                    '"server server.tld" - assign new mastodon instance\n' +
                    '"disable" or "d" - temporary disable notifications\n' +
                    '"enable" or "e" - enable notifications\n' +
                    '"replies on" - show replies in home feed\n' +
                    '"replies off" - do not show replies in home feed\n' +
                    '"autoboost <mastodon id>" or "ab <mastodon id>" - enable autoboost for <mastodon id>\n' +
                    '"info" or "i" - information about account\n',
                    mfrom='config@' + HOST,
                    mtype='chat')
                msg.send()
            elif body == 'disable' or body == 'd':
                try:
                    users_db.set_status_by_jid(user['jid'], 'disabled')
                    mastodon = mastodon_listeners.get(user['mid'])
                    print("mastodon=mastodon_listeners[user['mid']]")
                    print(mastodon)
                    mastodon.remove_jid(message['jid'])
                    print("mastodon.jids.remove(message['jid'])")
                    print(mastodon.jids)
                    if len(mastodon.jids) < 1:
                        print("closing stream")
                        mastodon.close_listener()
                        print("mastodon.close_listener()")
                        mastodon_listeners.pop(user['mid'])
                        print("mastodon_listeners.pop(user['mid'])")
                except (KeyError, AttributeError) as e:
                    print("Error:", str(e))
                    print("user['mid']=", user['mid'])
                    print('===')
                    print("listener not found")
                    print(user['mid'])
                    print("Full list of listeners:")
                    for k, v in mastodon_listeners.items():
                        print("\t", k, end=':')
                        print(v.jids)
                    print('===')
                msg = XMPP.make_message(
                    message['jid'],
                    'Message delivery is DISABLED',
                    mfrom='config@' + HOST,
                    mtype='chat')
                msg.send()
            elif body == 'enable' or body == 'e':
                try:
                    users_db.set_status_by_jid(user['jid'], 'enabled')
                    mastodon = mastodon_listeners.get(user['mid'])
                    mastodon.add_jids([message['jid']])
                except (KeyError, AttributeError):
                    m = MastodonUser(user.get('mid'), user.get('token'))
                    m.add_jids([user['jid']])
                    if(m.create_listener(update_queue, notification_queue)):
                        mastodon_listeners[user.get('mid')] = m
                msg = XMPP.make_message(
                    message['jid'],
                    'Message delivery is ENABLED',
                    mfrom='config@' + HOST,
                    mtype='chat')
                msg.send()
                print('=== enable')
                print(user['mid'])
                print("Full list of listeners:")
                for k, v in mastodon_listeners.items():
                    print("\t", k, end=':')
                    print(v.jids)
                print('===')
            elif body == 'info' or body == 'i':
                msg = XMPP.make_message(
                    message['jid'],
                    "your mastodon account is: " +
                    user['mid'],
                    mfrom='config@' + HOST,
                    mtype='chat')
                msg.send()
            elif re.match(r'^(autoboost|ab)(\W+|$)', body):
                try:
                    print('autoboost')
                    accts = re.sub(r'(autoboost|ab)(\W+)?', '', body, re.I)
                    print(accts)
                    l = users_db.getAutoboostByJid(message['jid'])
                    print(l)
                    if not accts:
                        msg = XMPP.make_message(
                            message['jid'],
                            "autobust is enabled for the following accounts:\n" +
                            "\n".join(l),
                            mfrom='config@' + HOST,
                            mtype='chat')
                        msg.send()
                        return
                    q = re.search(r'(.+?@.+)(?:[ ,;]+)?', accts)
                    print(q)
                    if q:
                        print("got mid")
                        for a in q.groups():
                            a = '@' + a
                            print(a)
                            if a not in l:
                                if a:
                                    users_db.addAutoboostToJid(a, message['jid'])
                            else:
                                print("going to delete " + str(a))
                                if a:
                                    users_db.delAutoboostByJid(a, message['jid'])
                    l = users_db.getAutoboostByJid(message['jid'])
                    msg = XMPP.make_message(
                        message['jid'],
                        "autobust is enabled for the following accounts:\n" +
                        "\n".join(l),
                        mfrom='config@' + HOST,
                        mtype='chat')
                    msg.send()
                except Exception as e:
                    print(str(e))
            elif re.match(r'replies', body):
                print("replies")
                res = re.match(r'replies\W+(.*)', body, re.I)
                message_text = 'Unknown command'
                try:
                    # print("replies "+ str(res[1]))
                    print(str(user))
                    if res[1] == 'on':
                        users_db.set_receive_replies_by_mid(user['mid'], 1)
                        message_text = 'Now you will receive replies in home feed'
                    elif res[1] == 'off':
                        users_db.set_receive_replies_by_mid(user['mid'], 0)
                        message_text = 'Now you will NOT receive replies in home feed'
                except Exception as e:  # NoneType
                    print("error:" + str(e))
                    u = users_db.get_user_by_jid(message['jid'])
                    print(str(u))
                    if u['receive_replies'] == '1':
                        message_text = "You receive replies in home feed"
                    else:
                        message_text = "You do not receive replies in home feed"
                msg = XMPP.make_message(
                    message['jid'],
                    message_text,
                    mfrom='config@' + HOST,
                    mtype='chat')
                msg.send()
            elif body == 'users' and user['jid'] == ADMIN_JID:
                message_text=''
                for k,v in mastodon_listeners.items():
                    if v.stream and v.stream.is_alive():
                        message_text = message_text + k + '\n'
                msg = XMPP.make_message(
                    message['jid'],
                    message_text,
                    mfrom='config@' + HOST,
                    mtype='chat')
                msg.send()
            elif body == 'stop' and user['jid'] == ADMIN_JID:
                global RUN
                RUN = 0
                for k, v in mastodon_listeners.items():
                    v.close_listener()
                msg = XMPP.make_message(
                    message['jid'],
                    "Bye",
                    mfrom='config@' + HOST,
                    mtype='chat')
                msg.send()
                # XMPP.send_offline()
                # XMPP.disconnect()
            elif body == 'threads' and user['jid'] == ADMIN_JID:
                msg = XMPP.make_message(
                    message['jid'],
                    str(threading.active_count()),
                    mfrom='config@' + HOST,
                    mtype='chat')
                msg.send()


async def process_xmpp(event):
    asyncio.current_task().set_name('process_xmpp')
    print("process xmpp")
    while RUN:
        try:
            # print("px")
            message = xmpp_queue.get(block=False)
            print("xmpp queue is not empty")
            body = message['body']
            if body:
                print('got xmpp message from ' + message['jid'])
                if message['to'].startswith('home@'):
                    process_xmpp_home(message)
                elif message['to'].startswith('new@'):
                    process_xmpp_new(message)
                elif re.search(r'\d+@', message['to']):  # reply to thread
                    process_xmpp_thread(message)
                elif message['to'].startswith('config@'):
                    process_xmpp_config(message)
                elif re.search(r'.+|new@', message['to']):  # new post to group
                    res = re.match(r'(.+)\|new@', message['to'])
                    group = res.group(1)
                    _group = group.replace('#', '@')
                    if not _group.startswith("@"):
                        _group = '@' + _group
                    print("writing in group " + _group)
                    message['body'] = _group + ' ' + message['body']
                    process_xmpp_new(message)


            else:  # It's a command
                command = message.get('command')
                user = users_db.get_user_by_jid(message['jid'])
                # print(user)
                if not user:
                    next
                try:
                    mastodon = mastodon_listeners[user['mid']]
                    if not mastodon:
                        next
                    if command == 'unsubscribe':
                        print("Unsubscribe from", message['jid'])
                        mastodon.jids.remove(message['jid'])
                        print("trying to delete user", message['jid'])
                        users_db.del_user_by_jid(message['jid'])
                        message_store.del_messages_by_mid(user['mid'])
                        print(mastodon.jids)
                        if len(mastodon.jids) < 1:
                            print("closing stream")
                            mastodon.close_listener()
                            mastodon_listeners.pop(user['mid'])
                except AttributeError:
                    pass
                except ValueError:
                    print("jid" + message['jid'] + " not found")
                except KeyError:
                    print("listener for " + user['mid'] + " not found")
                except TypeError:
                    print("no such user")

        except mastodon_listener.NotFoundError:
            print("ml error")
            msg = XMPP.make_message(
                message['jid'],
                "Message not found",
                mtype='chat',
                mfrom=message['to'])
            msg.send()
        except Empty:
            await asyncio.sleep(.2)
            
        except Exception as e:
            print(str(e))
            msg = XMPP.make_message(
                message['jid'],
                str(e),
                mtype='chat',
                mfrom=message['to'])
            msg.send()
    print(asyncio.current_task().get_name(),
        'is closed')


async def check_timeout(event):
    asyncio.current_task().set_name('check_timeout')
    while RUN:
        tasks = asyncio.all_tasks()
        if len(tasks) < 4:
            for t in tasks:
                try:
                    print(t.get_name())
                except Exception as e:
                    print("Exception:", e)
            try:
                print("Task Crashed")
                msg = XMPP.make_message(
                    ADMIN_JID,
                    'Task crashed',
                    mtype='chat',
                    mfrom='alerts@' + HOST)
                msg.send()
                #XMPP.disconnect()
            except Exception as e:
                print(e)
        await asyncio.sleep(2)
    print(asyncio.current_task().get_name(),
        'is closed')


def disconnected(s):
    print("disconnected: " + str(s))
    exit(1)

def process_process():
    while RUN:
        for k,v in mastodon_listeners.items():
            if v.stream and ( not v.stream.is_alive() ):
                print("I see a stream is not alive")
                sleep(2)
                v.create_listener(update_queue, notification_queue)
        sleep(2)
    XMPP.send_offline(ADMIN_JID)
    XMPP.disconnect()
    print('process_process is closed')

def mastodon_processor(login, v):
    print("mastodon processor")
    print(threading.current_thread().name)
    global mastodon_listeners
    m = MastodonUser(login, v.get('token'))
    m.add_jids(v.get('jids'))
    if(m.create_listener(update_queue, notification_queue)):
        mastodon_listeners[login] = m
    print("Full list of listeners:")
    for k, v in mastodon_listeners.items():
        print("\t", k, end=':')
        print(v.jids)
    print('===')

def mastodon_register_process(server, jid):
    try:
        users_db = db.Db(USERS_DB)
        print("trying to connect to", server, end='')
        mastodon = MastodonUser(server, None)
        print(" ok")
        print("Register server...", end='')
        url = mastodon.start_register(server)
        print(" ok")
        print("Adding user to db...", end='')
        users_db.add_user(jid,
                          server,
                          'Fake token'
                          )
        print(" ok")
        print("Setting user's status to 'registration'...", end='')
        users_db.set_status_by_jid(
            jid,
            'registration'
        )
        print(" ok")
        print("Sending auth link...", end='')
        msg = XMPP.make_message(
            jid,
            'please open the link, get code and paste it here\n' + url,
            mfrom='config@' + HOST,
            mtype='chat')
        print(" ok")
        mastodon_listeners[jid] = mastodon
    except Exception as e:
        msg = XMPP.make_message(
            jid,
            'Could not connect to ' + server + ' ' + str(e),
            mfrom='config@' + HOST,
            mtype='chat')
    msg.send()

def mastodon_register_finish_process(jid, code):
    m = mastodon_listeners.get(jid)
    token = m.finish_register(code)
    if token:
        res = m.verify_account()
    else:
        msg = XMPP.make_message(
            message['jid'],
            'Token is invalid. Please check the token',
            mfrom='config@' + HOST,
            mtype='chat')
        msg.send()
        return
    print(res)
    if res:
        users_db = db.Db(USERS_DB)
        user = users_db.get_user_by_jid(jid)
        mid = res['acct'] + '@' + user['mid']
        users_db.set_token_by_jid(user['jid'], token)
        users_db.set_mid_by_jid(user['jid'], mid)
        users_db.set_status_by_jid(user['jid'], 'enabled')
        if mastodon_listeners.get(mid):  # the listener is exist
            _m = mastodon_listeners.get(mid)
            _m.add_jids([user['jid']])
        else:
            try:
                mastodon_listeners.pop(user['jid'])
            except KeyError:
                pass
            m.add_jids([user['jid']])
            m.update_mid(mid)
            if(m.create_listener(update_queue, notification_queue)):
                mastodon_listeners[mid] = m
        msg = XMPP.make_message(
            jid,
            'You have registered\n' +
            'Your account is @' + mid,
            mfrom='config@' + HOST,
            mtype='chat')
        msg.send()
        XMPP.register_new_user(jid)
    else:
        msg = XMPP.make_message(
            jid,
            'Token is invalid. Please check the token',
            mfrom='config@' + HOST,
            mtype='chat')
        msg.send()

def _mastodon_process_reply_process(mid, mes_x, message, tp='update'):
    users_db = db.Db(USERS_DB)
    #user = users_db.get_user_by_jid(jid)
    #user = users.getUsersByMid(mid)[0]
    #if not user:
    #    return
    mastodon = mastodon_listeners.get(mid)
    #message_store = MessageStore(MESSAGES_DB)
    #message_store = MessageStore(MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USERNAME, MYSQL_PASSWORD)
    message_store = getMessageStore()
    if not mastodon:
        return
    _m = message
    if tp == 'update': 
        print("update")
        print("mid:", mid)
        print("type", _m.type)
        if _m.type == 'mention': # we will receive it via notification again
            print("Not for update handler. Returning")
            return
        if mid in _m.mentions:
            print("Receiver is in mentions. Ignoring update, we will receive it via notification")
            return
    net_tries = 3
    stored_message = None
    thread_id = None
    if _m.in_reply_to_id:
        search_for = _m.in_reply_to_id
    else:
        search_for = mes_x
    while True:
        try:
            print("search for message id", str(search_for))
            thread_messages = mastodon.get_thread(search_for)
            first_message = thread_messages[0]
            stored_message = message_store.get_message_by_id(first_message.id)
            print("thead", first_message.id)
            thread_id = first_message.id
            break
        except mastodon_listener.NetworkError:
            print("Network error. Retry...")
            print(mes_x)
            print(HOST)
            net_tries -= 1
            if net_tries < 1:
                print("Network error. Abort...")
                print(mes_x)
                print(HOST)
                return
        except mastodon_listener.NotFoundError:
            print("not found", str(search_for))
            break

    print("Process_reply")
    print(_m.to_dict())
    if stored_message:
        print("found")
        # message_store.update_mentions(first_message.id,_m.mentions)
        # mentions_str = stored_message['mentions']
        # mentions = set(mentions_str.split(' '))
        mentions = _m.mentions
        if '@' + mid in _m.mentions or ((stored_message['mentions'].split(' '))[0] == '@'+mid):
            print("answer to known message")
            for j in mastodon.jids:
                msg = XMPP.make_message(j,
                                        _m.text,
                                        mfrom=str(first_message.id) + '@' + HOST,
                                        mtype='chat')
                msg.send()
            message_store.add_message(
                    _m.text,
                    _m.url,
                    _m.from_mid,
                    _m.mentions,
                    _m.visibility,
                    _m.id,
                    mid,
                    _m.date,
                    first_message.id
                )
        else:
            print("unknown message. Not to me")
            for j in mastodon.jids:
                # check if user has disabled replies receiving
                u = users_db.get_user_by_jid(j)
                if (u and u['receive_replies'] == '1') or tp == 'notification':
                    msg = XMPP.make_message(j,
                                            _m.text,
                                            mfrom='home@' + HOST,
                                            mtype='chat')
                    msg.send()
                    message_store.add_message(
                        _m.text,
                        _m.url,
                        _m.from_mid,
                        _m.mentions,
                        _m.visibility,
                        _m.id,
                        mid,
                        _m.date
                    )
                else:
                    print("Reply will not be delivered. Reply delivery is disabled")
    else:
        if '@' + mid in _m.mentions:
            if not thread_id:
                thread_id = _m.id
            for j in mastodon.jids:
                msg = XMPP.make_message(j,
                                        _m.text,
                                        mfrom= str(thread_id) + '@' + HOST,
                                        mtype='chat')
                msg.send()
            message_store.add_message(
                    _m.text,
                    _m.url,
                    _m.from_mid,
                    _m.mentions,
                    _m.visibility,
                    _m.id,
                    mid,
                    _m.date,
                    thread_id
                )
        else:
            for j in mastodon.jids:
                # check if user has disabled replies receiving
                u = users_db.get_user_by_jid(j)
                if (u and u['receive_replies'] == '1') or tp == 'notification':
                    msg = XMPP.make_message(j,
                                            _m.text,
                                            mfrom='home@' + HOST,
                                            mtype='chat')
                    msg.send()
                    message_store.add_message(
                        _m.text,
                        _m.url,
                        _m.from_mid,
                        _m.mentions,
                        _m.visibility,
                        _m.id,
                        mid,
                        _m.date
                    )
    
def mastodon_get_thread_process(jid, mes_x):
    users_db = db.Db(USERS_DB)
    user = users_db.get_user_by_jid(jid)
    if not user:
        return
    mastodon = mastodon_listeners.get(user['mid'])
    if not mastodon:
        return
    try:
        thread_messages = mastodon.get_thread(mes_x)
    except mastodon_listener.NetworkError:
        print("error in main")
        print(jid)
        print(mes_x)
        print(HOST)
        msg = XMPP.make_message(
            jid,
            "Network error",
            mtype='chat',
            mfrom=str(mes_x) + '@' + HOST)
        msg.send()
        return
    if len(thread_messages) < 1:
        # raise mastodon_listener.NotFoundError()
        msg = XMPP.make_message(
            jid,
            "Message not found",
            mtype='chat',
            mfrom=str(thread_messages[0].id) + '@' + HOST)
        msg.send()
        return
    # message_store = MessageStore(MESSAGES_DB)
    # message_store = MessageStore(MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USERNAME, MYSQL_PASSWORD)
    message_store = getMessageStore()
    for _m in thread_messages:
        print(_m.to_dict())
        #_m.mentions.remove(_m.from_mid)
        message_store.add_message(
            _m.text,
            _m.url,
            _m.from_mid,
            _m.mentions,
            _m.visibility,
            _m.id,
            user['mid'],
            _m.date,
            thread_messages[0].id
        )
        msg = XMPP.make_message(
            jid,
            _m.text,
            mtype='chat',
            mfrom=str(thread_messages[0].id) + '@' + HOST)
        msg.send()
        
def mastodon_post_status_process(jid, in_reply_to_id, status, visibility):
    users_db = db.Db(USERS_DB)
    user = users_db.get_user_by_jid(jid)
    if not user:
        return
    mastodon = mastodon_listeners.get(user['mid'])
    if not mastodon:
        return
    try:
        if in_reply_to_id:
            message_store = getMessageStore()
            #message_store = SqliteStore(MESSAGES_DB)
            #message_store = MessageStore(MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USERNAME, MYSQL_PASSWORD)
            last_message = message_store.get_message_by_id(in_reply_to_id)
            mentions=[]
            if last_message:
                feed = last_message.get('feed','home')
                mentions = last_message['mentions'].lower().split(' ')
                print('last_messsage')
                print(last_message)
            author = ''
            try:
                # author = mentions.pop(0) + ' '  # Space is matter!
                # if author == '@' + user['mid'].lower():
                #     author = ''
                while mentions.count('@' + user['mid'].lower()):
                    mentions.remove('@' + user['mid'].lower())
            except ValueError:
                pass
            # mentions.append(author)
            toot = mastodon.status_post(status=status, in_reply_to_id=in_reply_to_id, visibility=visibility)
            message_store.add_message(
                status,
                toot['url'],
                '@' + user['mid'].lower(),
                mentions,
                visibility,
                toot['id'],
                user['mid'],
                toot['created_at'],
                feed
            )
        else:
            mastodon.status_post(status=status, visibility=visibility)
    except mastodon_listener.NetworkError:
        print("error in main")
        print(jid)
        if in_reply_to_id:
            feed = last_message.get('feed','new')
            msg = XMPP.make_message(
                jid,
                "Cannot send post, network error.",
                mtype='chat',
                mfrom=feed + '@' + HOST)
        else:    
            msg = XMPP.make_message(
                jid,
                "Cannot send post, network error",
                mtype='chat',
                mfrom='new@' + HOST)
        msg.send()
    except mastodon_listener.APIError as e:
        msg = XMPP.make_message(
            jid,
            str(e),
            mtype='chat',
            mfrom='new' + '@' + HOST)
        msg.send()
    
def mastodon_reblog_fav_status_process(action, jid, mes_x):
    users_db = db.Db(USERS_DB)
    user = users_db.get_user_by_jid(jid)
    if not user:
        return
    mastodon = mastodon_listeners.get(user['mid'])
    if not mastodon:
        return
    try:
        if action == 'r':
            _m = mastodon.status_reblog(mes_x)
        else:
            _m = mastodon.status_favourite(mes_x)
    except mastodon_listener.NetworkError:
        print("error in main")
        print(jid)
        print(mes_x)
        print(HOST)
        msg = XMPP.make_message(
            jid,
            "Network error",
            mtype='chat',
            mfrom=str(mes_x) + '@' + HOST)
        msg.send()
        return
    if _m:
        msg = XMPP.make_message(
            jid,
            _m.text,
            mtype='chat',
            mfrom='home@' + HOST)
        msg.send()
        
if __name__ == '__main__':
#def xmpp_processor(xmpp_queue):
    xmpp_queue = Queue()
    users_db = db.Db(USERS_DB)
    # message_store = MessageStore(MESSAGES_DB)
    # message_store = MessageStore(MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USERNAME, MYSQL_PASSWORD)
    message_store = getMessageStore()
    users = users_db.get_users()  # {jid, mid, token}
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # loop = asyncio.get_event_loop()
    XMPP = gxmpp.Component(xmpp_jid, xmpp_password, xmpp_server, xmpp_port)
    XMPP.add_users(users)
    XMPP.attach_queue(xmpp_queue)
    XMPP.connected_event = asyncio.Event()
    callback = lambda _: XMPP.connected_event.set()
    XMPP.add_event_handler('session_start', callback)
    XMPP.add_event_handler('session_start', process_update)
    XMPP.add_event_handler('session_start', process_xmpp)
    XMPP.add_event_handler('session_start', process_notification)
    XMPP.add_event_handler('session_start', check_timeout)
    XMPP.add_event_handler('disconnected', disconnected)

    XMPP.register_plugin('xep_0030')  # Service Discovery
    XMPP.register_plugin('xep_0065', {
        'auto_accept': True
    })  # SOCKS5 Bytestreams
    print("waiting for xmpp connect")
    MTHREADS = list()
    users_db = db.Db(USERS_DB)
    users = users_db.get_users()  # {jid, mid, token}
    print(users)
    USER_LIST = get_uniq_mids(users)
    for k, v in USER_LIST.items():
        #mastodon_processor(k,v)
        t = threading.Thread(target=mastodon_processor, args=(k, v), name='mastodon_listener_'+str(k))
        t.start()
        MTHREADS.append(t)
    XMPP.connect()
    print("after loop")
    print("xmmp connected")
    t = threading.Thread(target=process_process, name="process_process")
    t.start()
    MTHREADS.append(t)
    #try:
    loop.run_until_complete(XMPP.disconnected)
    print("end loop")
    #finally:
        #loop.stop()
        #asyncio.set_event_loop(None)
    #XMPP.process()

# if __name__ == '__main__':
#     xmpp_t = threading.Thread(target=xmpp_processor, args=(xmpp_queue,), name='xmpp')
#     xmpp_t.start()
