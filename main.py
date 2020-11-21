#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import sys
sys.path.append('./venv/lib/python3.7/site-packages')

import mastodon_listener
from message_store import MessageStore
from queue import Empty, Queue
from mastodon_listener import MastodonUser
# import command_parser
import re
import gxmpp
import json
import db
import time

import config

SERVICE_NAME = config.SERVICE_NAME
HOSTNAME =  config.HOSTNAME
HOST=SERVICE_NAME+'.'+HOSTNAME
xmpp_jid = HOST
USERS_DB = config.USERS_DB
MESSAGES_DB = config.MESSAGES_DB
xmpp_password = config.XMPP_PASSWORD
xmpp_server = config.XMPP_SERVER
xmpp_port = config.XMPP_PORT
xmpp_queue=Queue()
notification_queue=Queue()
update_queue=Queue()


def get_uniq_mids(users:list) -> dict:
    mu={}
    for u in users:
        if not mu.get(u['mid']):
            mu[u['mid']]={}
            mu[u['mid']]['jids']=list([u['jid']])
            mu[u['mid']]['token']=u['token']
        else:
            mu[u['mid']]['jids'].append(u['jid'])
    return mu
     
def get_mentions(thread:list) -> str:
    mentions=set()
    for m in thread:
        mentions.update(m.mentions)
    return " ".join(mentions)

async def process_update(event):
    while 1:
        try:
            message = update_queue.get(block=False)
            _m=message['status']
            print("mid:",message['mid'])
            print("mentions:", _m.mentions)
            answer_to_known_message=0
            if _m.in_reply_to_id:
                thread=message['m'].get_thread(_m.id)
                first_message=thread[0]
                stored_message=message_store.get_message_by_id(first_message.id)
                if stored_message:
                    message_store.update_mentions(first_message.id,_m.mentions)
                    mentions_str=stored_message['mentions']
                    mentions=set(mentions_str.split(' '))
                    if message['mid'] in mentions:
                        answer_to_known_message=1
            else:
                #autobost processing
                try:
                    print("autoboost processing")
                    for j in message['m'].jids:
                        print("for "+str(j))
                        l=users_db.getAutoboostByJid(j)
                        print("autoboost names:\n"+str(l))
                        print("post from "+str(_m.from_mid))
                        if _m.from_mid.lower() in l:
                            print("got reblog")
                            mastodon=mastodon_listeners.get(message['mid'])
                            if mastodon:
                                mastodon.status_reblog(_m.id)
                except Exception as e:
                    print(str(e))
            if answer_to_known_message:
                for j in message['m'].jids:
                    msg = XMPP.make_message(j,
                                    _m.text,
                                    mfrom=str(first_message.id)+'@'+HOST,
                                    mtype='chat')
                    msg.send()
            else:
                if '@'+message['mid'] not in _m.mentions:
                    message_store.add_message(
                        _m.text,
                        _m.url,
                        _m.mentions,
                        _m.visibility,
                        _m.id,
                        message['mid']
                    )
                    for j in message['m'].jids:
                        msg = XMPP.make_message(j,
                                            _m.text,
                                            mfrom='home@'+HOST,
                                            mtype='chat')
                        msg.send()
                else:
                    print("recipient is in mentions. Ignored")
                    print("from_id=",_m.from_mid)
                    print("to:", message['mid'])
                    print("in reply to ",_m.in_reply_to_id)
                    if ( not _m.in_reply_to_id ) and _m.from_mid == message['mid']:
                        print("Our own new message. Putting it in home chat")
                        message_store.add_message(
                            _m.text,
                            _m.url,
                            _m.mentions,
                            _m.visibility,
                            _m.id,
                            message['mid']
                        )
                        for j in message['m'].jids:
                            msg = XMPP.make_message(j,
                                                _m.text,
                                                mfrom='home@'+HOST,
                                                mtype='chat')
                            msg.send()
                    # No need to send message. We will receive a duplicate via notification
                    #pass
        except Empty:
            pass
        await asyncio.sleep(.2)

async def process_notification(event):
    while 1:
        try:
            message = notification_queue.get(block=False)
            _m=message['status']
            print("\n\n====")
            print(_m.to_dict())
            print("====\n\n\n")
            if _m.type == 'mention':
                ok=1
                if _m.in_reply_to_id:
                    print("reply to id:",_m.in_reply_to_id)
                    try:
                        thread = message['m'].get_thread(_m.in_reply_to_id)
                    except mastodon_listener.NotFoundError:
                        print("not found", _m.in_reply_to_id)
                        #try:
                            #thread=m.search(mm['url'])
                            #_m=process_update(thread,to_mastouser)
                            #thread = m.status_context(_m.get('id'))
                        #except MastodonNotFoundError:
                        print("not found",_m.url)
                        ok=0
                    if ok and thread:
                        for j in message['m'].jids:
                            msg = XMPP.make_message(
                                j,
                                _m.text,
                                mtype='chat',
                                mfrom=str(thread[0].id) + "@"+HOST)
                            msg.send()
                    else:
                        for j in message['m'].jids:
                            msg = XMPP.make_message(
                            j,
                            _m.text,
                            mtype='chat',
                            mfrom=str(_m.id) + "@"+HOST)
                            msg.send()
                else:
                    message_store.add_message(
                             _m.text,
                             _m.url,
                             _m.mentions,
                             _m.visibility,
                             _m.id,
                             message['mid'],
                             thread[0].id
                         )
                    for j in message['m'].jids:
                        msg = XMPP.make_message(
                            j,
                            _m.text,
                            mtype='chat',
                            mfrom=str(_m.id) + "@"+HOST)
                        msg.send()
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
                        mfrom='home@'+HOST)
                    msg.send()
        except Empty:
            pass
        #print('process_notification')
        await asyncio.sleep(.2)

def process_xmpp_home(message):
    user=users_db.get_user_by_jid(message['jid'])
    if not user:
        return
    mastodon=mastodon_listeners.get(user['mid'])
    if not mastodon:
        msg = XMPP.make_message(
            message['jid'],
            'Seems like you have not registered or internal exception accured'
            ,
            mfrom='home@' + HOST,
            mtype='chat')
        msg.send()
        return
    body=message['body']
    if re.match(r'h(elp)?$', body, re.I|re.MULTILINE):
        help_message='''HELP
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
        msg = XMPP.make_message(
                message['jid'],
                help_message,
                mtype='chat',
                mfrom='home@'+HOST)
        msg.send()
    elif re.match(r'\.(\d{1,2})?$', body, re.I|re.MULTILINE):
        res=re.findall(r'^\.(\d+)', body)
        h_id=0
        if res:
            h_id=int(res[0])
        print("Going to get message",h_id)
        ms=message_store.get_messages_for_user(user['mid'])
        if h_id >= len(ms):
            raise mastodon_listener.NotFoundError()
        mes_x=ms[h_id]
        print("Got message! mid=",mes_x)
        thread_messages=mastodon.get_thread(mes_x)
        if len(thread_messages) < 1:
            raise mastodon_listener.NotFoundError()
        for _m in thread_messages:
            print(_m)
            msg = XMPP.make_message(
                message['jid'],
                _m.text,
                mtype='chat',
                mfrom=str(thread_messages[0].id)+'@'+HOST)
            msg.send()
    elif re.match(r'r(\d{1,2})?$', body, re.I|re.MULTILINE):
        res=re.findall(r'^r(\d+)', body, re.I)
        h_id=0
        if res:
            h_id=int(res[0])
        print("Going to get message",h_id)
        ms=message_store.get_messages_for_user(user['mid'])
        if h_id >= len(ms):
            raise mastodon_listener.NotFoundError()
        mes_x=ms[h_id]
        _m=mastodon.status_reblog(mes_x)
        if _m:
            msg = XMPP.make_message(
                message['jid'],
                _m.text,
                mtype='chat',
                mfrom='home@'+HOST)
            msg.send()
    elif re.match(r'f(\d{1,2})?$', body, re.I|re.MULTILINE):
        res=re.findall(r'^f(\d+)', body, re.I)
        h_id=0
        if res:
            h_id=int(res[0])
        print("Going to get message",h_id)
        ms=message_store.get_messages_for_user(user['mid'])
        if h_id >= len(ms):
            raise mastodon_listener.NotFoundError()
        mes_x=ms[h_id]
        _m=mastodon.status_favourite(mes_x)
        if _m:
            msg = XMPP.make_message(
                message['jid'],
                _m.text,
                mtype='chat',
                mfrom='home@'+HOST)
            msg.send()
    elif re.match(r'w(\d{1,2})?$', body, re.I|re.MULTILINE):
        res=re.findall(r'^w(\d+)', body, re.I)
        h_id=0
        if res:
            h_id=int(res[0])
        print("Going to get link to message",h_id)
        ms=message_store.get_messages_for_user(user['mid'])
        if h_id >= len(ms):
            raise mastodon_listener.NotFoundError()
        mes_x=message_store.get_message_by_id(ms[h_id])
        if mes_x:
            msg = XMPP.make_message(
                message['jid'],
                mes_x['url'],
                mtype='chat',
                mfrom='home@'+HOST)
            msg.send()
    elif re.match(r'(?:>|»)', body, re.I|re.MULTILINE):
        print("quotation")
        strings=body.split('\n')
        print(strings)
        original_post=''
        while len(strings) > 0:
            l = strings.pop(0)
            q=re.search(r'(?:>|») ?(.+)', l)
            if q and q.group(1):
                original_post+=q.group(1)+'\n'
            else:
                strings.append(l) # return a string back
                break #end of quotation
        print('Original post was:')
        original_post.rstrip()
        print(original_post)
        toot=message_store.find_message(original_post)
        if not toot:
            raise mastodon_listener.NotFoundError()
        message_id=toot['id']
        command="\n".join(strings)
        if command == '.' or command == '': #get thread
            thread_messages=mastodon.get_thread(message_id)
            for _m in thread_messages:
                msg = XMPP.make_message(
                message['jid'],
                _m.text,
                mtype='chat',
                mfrom=str(thread_messages[0].id) + '@' + HOST)
                msg.send()
        elif command.lower() == 'r': #reblog status
            _m=mastodon.status_reblog(message_id)
            if _m:
                msg = XMPP.make_message(
                    message['jid'],
                    _m.text,
                    mtype='chat',
                    mfrom='home@'+HOST)
                msg.send()
        elif command.lower() == 'f': #favourite status
            _m=mastodon.status_favourite(message_id)
            if _m:
                msg = XMPP.make_message(
                    message['jid'],
                    _m.text,
                    mtype='chat',
                    mfrom='home@'+HOST)
                msg.send()
        elif command.lower() == 'w': #get link
            msg = XMPP.make_message(
                message['jid'],
                toot['url'],
                mtype='chat',
                mfrom='home@'+HOST)
            msg.send()
    else:
        msg = XMPP.make_message(
                message['jid'],
                'Unknown command\n'+
                'If you want to write new post then please send your message to contact new@{0}'.format(HOST),
                mtype='chat',
                mfrom='home@'+HOST)
        msg.send()

def process_xmpp_new(message):
    user=users_db.get_user_by_jid(message['jid'])
    if not user:
        return
    mastodon=mastodon_listeners[user['mid']]
    if not mastodon:
        return
    body=message['body']
    try:
        mastodon.status_post(
            status=body,
            visibility='public'
        )
        # mastodon.on_update(new_toot)
    except mastodon_listener.APIError as e:
        msg = XMPP.make_message(
                    user['jid'],
                    str(e),
                    mtype='chat',
                    mfrom='new'+'@'+HOST)
        msg.send()
    except BaseException as e:
        print("error:"+str(e))
        

def process_xmpp_thread(message):
    user=users_db.get_user_by_jid(message['jid'])
    if not user:
        return
    mastodon=mastodon_listeners[user['mid']]
    if not mastodon:
        return
    mid=re.findall(r'(\d+)@',message['to'])[0]
    print(mid)
    body = message['body']
    if body == '.':
        print("get thread")
        thread = mastodon.get_thread(mid)
        #print(thread)
        for m in thread:
            msg = XMPP.make_message(
                message['jid'],
                m.text,
                mfrom=str(thread[0].id) + '@' + HOST,
                mtype='chat')
            msg.send()
    elif body.upper() == 'W': # Get link
        #TODO: change dict to EncodedMessage type
        toot=message_store.get_message_by_id(mid)
        if not toot:
            print("no toot in message store. Getting from mastodon...")
            toot=mastodon.get_status(mid)
            if not toot:
                raise mastodon_listener.NotFoundError
        try:
            print(type(toot))
            if type(toot)==dict:
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
    elif body.upper() == 'RR': #Reblog first message
        # toot=message_store.get_message_by_id(mid)
        # if not toot:
        #     toot=mastodon.get_status(mid)
        _m=mastodon.status_reblog(mid)
        msg = XMPP.make_message(
            message['jid'],
            _m.text,
            mtype='chat',
            mfrom='home@'+HOST)
        msg.send()
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
        
    elif body.upper() == 'H': # Get help
        msg = XMPP.make_message(
            message['jid'],
            'HELP\n' +
            'w - get link\n' +
            '. - get full thread\n' +
            # 'r - reblog LAST received message in thread\n'+
            'rr - reblog FIRST message in thread\n' + 
            'h - this help\n' +
            'text - post answer'
            ,
            mfrom=str(mid) + '@' + HOST,
            mtype='chat')
        msg.send()
    else:
        if len(body) > 2: # Answer to post
            # toot=message_store.get_message_by_id(mid)
            try: # Answer to last message in the thread
                thread=mastodon.get_thread(mid)
                mentions_str=get_mentions(thread)
                mastodon.status_post(
                    status=mentions_str + ' ' + body,
                    in_reply_to_id=thread[-1].id,
                    visibility=thread[-1].visibility
                )
                message_store.update_mentions(
                    mid,
                    ['@'+user.get('mid')]
                )
            except mastodon_listener.APIError as e:
                msg = XMPP.make_message(
                message['jid'],
                str(e),
                mfrom=str(mid) + '@' + HOST,
                mtype='chat')
                msg.send()
        else: #seems like an error in command input
            msg = XMPP.make_message(
            message['jid'],
            'Unknown command\n' +
            'w - get link to thread\n' +
            '. - get full thread\n' +
            'rr - reblog FIRST message in thread\n' + 
            'h - this help\n' +
            'text - post answer'
            ,
            mfrom=str(mid) + '@' + HOST,
            mtype='chat')
            msg.send()

def process_xmpp_config(message):
    user=users_db.get_user_by_jid(message['jid'])
    body=message['body']
    if not user:
        body=body.lower()
        if body.startswith('server '):
            server=re.sub(r'server\W+','',body)
            msg = XMPP.make_message(
                   message['jid'],
                   'please wait, trying to connect to your server...',
                   mfrom='config@' + HOST,
                   mtype='chat')
            msg.send()
            try:
                print("trying to connect to",server, end='')
                mastodon=MastodonUser(server, None)
                print(" ok")
                print("Register server...", end='')
                url=mastodon.start_register(server)
                print(" ok")
                print("Adding user to db...", end='')
                users_db.add_user(message['jid'],
                                  server,
                                  'Fake token'
                                  )
                print(" ok")
                print("Setting user's status to 'registration'...", end='')
                users_db.set_status_by_jid(
                    message['jid'],
                    'registration'
                )
                print(" ok")
                print("Sending auth link...", end='')
                msg = XMPP.make_message(
                    message['jid'],
                    'please open the link, get code and paste it here\n' + url,
                    mfrom='config@' + HOST,
                    mtype='chat')
                print(" ok")
                mastodon_listeners[message['jid']]=mastodon
            except:
                msg = XMPP.make_message(
                    message['jid'],
                    'Could not connect to ' + server,
                    mfrom='config@' + HOST,
                    mtype='chat')
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
        if user['status']=='registration':
            if body.startswith('server ') or not mastodon_listeners.get(message['jid']):
                users_db.del_user_by_jid(message['jid'])
                process_xmpp_config(message)
                return
            code=body
            
            print("User in registration")
            m=mastodon_listeners[message['jid']]
            print("checking token with server",user['mid'])
            token=m.finish_register(code)
            if token:
                res=m.verify_account()
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
                mid=res['acct'] + '@' + user['mid']
                users_db.set_token_by_jid(user['jid'],token)
                users_db.set_mid_by_jid(user['jid'],mid)
                users_db.set_status_by_jid(user['jid'],'enabled')
                if mastodon_listeners.get(mid): # the listener is exist
                    _m=mastodon_listeners[mid]
                    _m.add_jids([user['jid']])
                else:
                    try:
                        mastodon_listeners.pop(user['jid'])
                    except KeyError:
                        pass
                    m.add_jids([user['jid']])
                    m.update_mid(mid)
                    m.create_listener(update_queue, notification_queue)
                    mastodon_listeners[mid] = m
                msg = XMPP.make_message(
                    message['jid'],
                    'You have registered\n' +
                    'Your account is @'+mid,
                    mfrom='config@' + HOST,
                    mtype='chat')
                msg.send()
                XMPP.register_new_user(message['jid'])
            else:
                msg = XMPP.make_message(
                message['jid'],
                'Token is invalid. Please check the token',
                mfrom='config@' + HOST,
                mtype='chat')
                msg.send()
        else:
            body=body.lower()
            if body.startswith('server '):
                try:
                    mastodon=mastodon_listeners[user['mid']]
                    users_db.del_user_by_jid(message['jid'])
                    mastodon.jids.remove(message['jid'])
                    if len(mastodon.jids) < 1:
                        print("closing stream")
                        mastodon.close_listener()
                        mastodon_listeners.pop(user['mid'])
                except (KeyError, AttributeError) as e:
                    print("Error deleting listener:", str(e) )
                    # pass
                process_xmpp_config(message)
            elif body == 'help':
                msg = XMPP.make_message(
                message['jid'],
                'HELP\n' +
                '"server server.tld" - assign new mastodon instance\n' +
                '"disable" or "d" - temporary disable notifications\n' +
                '"enable" or "e" - enable notifications\n' +
                '"info" or "i" - information about account',
                mfrom='config@' + HOST,
                mtype='chat')
                msg.send()
            elif body == 'disable' or body == 'd':
                try:
                    users_db.set_status_by_jid(user['jid'],'disabled')
                    mastodon=mastodon_listeners.get(user['mid'])
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
                    print("user['mid']=",user['mid'])
                    print('===')
                    print("listener not found")
                    print(user['mid'])
                    print("Full list of listeners:")
                    for k,v in mastodon_listeners.items():
                        print("\t",k, end=':')
                        print(v.jids)
                    print('===')
                msg = XMPP.make_message(
                    message['jid'] ,
                    'Message delivery is DISABLED',
                    mfrom='config@' + HOST,
                    mtype='chat')
                msg.send()
            elif body == 'enable' or body == 'e':
                try:
                    users_db.set_status_by_jid(user['jid'],'enabled')
                    mastodon=mastodon_listeners[user['mid']]
                    mastodon.add_jids([message['jid']])
                except (KeyError, AttributeError):
                    m=MastodonUser(user.get('mid'), user.get('token'))
                    m.add_jids([user['jid']])
                    m.create_listener(update_queue, notification_queue)
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
                for k,v in mastodon_listeners.items():
                    print("\t",k, end=':')
                    print(v.jids)
                print('===')
            elif body == 'info' or body == 'i':
                msg = XMPP.make_message(
                    message['jid'],
                    "your mastodon account is: "+
                    user['mid'],
                    mfrom='config@' + HOST,
                    mtype='chat')
                msg.send()
            elif re.match(r'^(autoboost|ab)(\W+|$)', body):
                try:
                    print('autoboost')
                    accts=re.sub(r'(autoboost|ab)(\W+)?','',body, re.I)
                    print(accts)
                    l=users_db.getAutoboostByJid(message['jid'])
                    print(l)
                    if not accts:
                        msg = XMPP.make_message(
                            message['jid'],
                            "autobust is enabled for the following accounts:\n"+
                            "\n".join(l),
                            mfrom='config@' + HOST,
                            mtype='chat')
                        msg.send()
                        return
                    q=re.search(r'(.+?@.+)(?:[ ,;]+)?', accts)
                    print(q)
                    if q:
                        print("got mid")
                        for a in q.groups():
                            print(a)
                            if a not in l:
                                if a:
                                    users_db.addAutoboostToJid(a,message['jid'])
                            else:
                                print("going to delete "+str(a))
                                if a:
                                    users_db.delAutoboostByJid(a,message['jid'])
                    l=users_db.getAutoboostByJid(message['jid'])
                    msg = XMPP.make_message(
                        message['jid'],
                        "autobust is enabled for the following accounts:\n"+
                        "\n".join(l),
                        mfrom='config@' + HOST,
                        mtype='chat')
                    msg.send()
                except Exception as e:
                    print(str(e))
                

async def process_xmpp(event):
    while 1:
        try:
            message = xmpp_queue.get(block=False)
            body = message['body']
            if body:
                print('got xmpp message from ' + message['jid'])
                if message['to'].startswith('home@'):
                    process_xmpp_home(message)
                elif message['to'].startswith('new@'):
                    process_xmpp_new(message)
                elif re.search(r'\d+@', message['to']): # reply to thread
                    process_xmpp_thread(message)
                elif message['to'].startswith('config@'):
                    process_xmpp_config(message)
            else: # It's a command
                command=message.get('command')
                user=users_db.get_user_by_jid(message['jid'])
                # print(user)
                if not user:
                    next
                try:
                    mastodon=mastodon_listeners[user['mid']]
                    if not mastodon:
                        next
                    if command == 'unsubscribe':
                        print("Unsubscribe from",message['jid'])
                        mastodon.jids.remove(message['jid'])
                        print("trying to delete user",message['jid'])
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
            msg = XMPP.make_message(
                message['jid'],
                "Message not found",
                mtype='chat',
                mfrom=message['to'])
            msg.send()
            
        except Empty:
            pass
        await asyncio.sleep(.2)

if __name__ == '__main__':
    XMPP=gxmpp.Component(xmpp_jid, xmpp_password, xmpp_server, xmpp_port)
    users_db = db.Db(USERS_DB)
    message_store=MessageStore(MESSAGES_DB)
    users = users_db.get_users()  # {jid, mid, token}
    print(users)
    XMPP.add_users(users)
    XMPP.attach_queue(xmpp_queue)
    loop=asyncio.get_event_loop()
    XMPP.connected_event = asyncio.Event()
    callback = lambda _: XMPP.connected_event.set()
    XMPP.add_event_handler('session_start', callback)
    XMPP.add_event_handler('session_start', process_update)
    XMPP.add_event_handler('session_start', process_notification)
    XMPP.add_event_handler('session_start', process_xmpp)
<<<<<<< HEAD
    xmpp.register_plugin('xep_0030') # Service Discovery
=======
    XMPP.register_plugin('xep_0030') # Service Discovery
>>>>>>> 4a87c7ac0256d8204d833bc7ccd4c49258cc00e9
    XMPP.register_plugin('xep_0065', {
        'auto_accept': True
    }) # SOCKS5 Bytestreams

    
    XMPP.connect()
    loop.run_until_complete(XMPP.connected_event.wait())
    print("xmmp connected")
    
    mastodon_listeners={}
    USER_LIST=get_uniq_mids(users)
    for k,v in USER_LIST.items():
        m=MastodonUser(k, v.get('token'))
        m.add_jids(v.get('jids'))
        m.create_listener(update_queue, notification_queue)
        mastodon_listeners[k] = m
    
    print("Full list of listeners:")
    for k,v in mastodon_listeners.items():
        print("\t",k, end=':')
        print(v.jids)
    print('===')

    XMPP.process()