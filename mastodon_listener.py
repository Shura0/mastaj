#!/bin/env python3


from mastodon import Mastodon, StreamListener,\
MastodonNotFoundError, MastodonAPIError, MastodonUnauthorizedError,\
MastodonNetworkError, MastodonIllegalArgumentError

# import time
from queue import Empty
from multiprocessing import Queue
import re
# import mq
import db
# import numpy as np
import json
import html_parser
import config
from time import time

LOG_FILE=config.LOG_FILE
TIMEOUT=30

def log(text:str):
    if config.LOGGING:
        with open(LOG_FILE, 'a') as f:
            f.write(text+'\n')

class NotFoundError(MastodonNotFoundError):
    pass

class APIError(MastodonAPIError):
    pass

class NetworkError(MastodonNetworkError):
    pass

class EncodedMessage:
    def __init__(self):
        self.id = 0
        self.in_reply_to_id = None
        self.type = ''
        self.mentions = set()
        self.url = ''
        self.visibility = ''
        self.text = ''
        self.from_mid = ''
    
    def add_mentions(self, *argv):
        for i in argv:
            if type(i) == list:
                for o in i:
                    self.mentions.add(o)
            elif type(i) == set:
                self.mentions.update(i)
            else:
                self.mentions.add(i)
    
    def to_dict(self):
        return {
            'id': self.id,
            'in_reply_to_id':self.in_reply_to_id,
            'type': self.type,
            'url': self.url,
            'mentions': self.mentions,
            'visibility': self.visibility,
            'text': self.text
        }
    

class MastodonListener(StreamListener):
    def __init__(self, mid):
        StreamListener.__init__(self)
        self.mid = mid
        self.lastbeat=int(time())
        self.got_heartbeat=0
        # self.update_q = update
        # self.message_q = message
        self.server_name=re.findall(r'([^@]+)$',self.mid)[0]
        print('new listener')

    def setMid(self, mid):
        self.mid = mid

    def process_update(self, status):
        data=status
        m = EncodedMessage()
        m.id=data['id']
        log("Update")
        log(str(status))
        # m['mentions'] = set()
        if data.get('reblog'):
            cont = data['reblog']
            acct=data['account']['acct']
            if not '@' in acct:
                acct=acct+'@'+self.server_name
            m.from_mid=acct
            acct=cont['account']['acct']
            if not '@' in acct:
                acct=acct+'@'+self.server_name
            m.add_mentions("@" + acct)
            to_out = "@{} reblog status of @{}:\n".format(
                data['account']['acct'],
                data['reblog']['account']['acct'])
        else:
            cont = data
            acct=data['account']['acct']
            if not '@' in acct:
                acct=acct+'@'+self.server_name
            m.from_mid=acct
            # m['mentions'].add("@" + acct)
            m.add_mentions("@" + acct)
            to_out = ''
        parser = html_parser.MyHTMLParser()
        print(cont['content'])
        cont['content']=re.sub(r'\n','',cont['content'])
        parser.feed(cont['content'])
        parser.close()
        text = parser.get_result()
        to_out += text
        if cont.get('spoiler_text'):
            parser.feed(cont['spoiler_text'])
            parser.close()
            text = parser.get_result()
            to_out = "Spoiler text: "+text+"\n"+to_out
        media_list = cont.get('media_attachments')
        for u in media_list:
            to_out += "\n" + u['url']
        mentions = cont.get('mentions')
        for a in mentions:
            if not '@' in a['acct']:
                a['acct']+='@'+self.server_name
            # m['mentions'].add('@' + a['acct'])
            m.add_mentions("@" + a['acct'])
        m.url = cont['url']
        m.visibility = cont['visibility']
        m.id = cont['id']
        if data.get('reblog'):
            m.text=to_out
        else:
            m.text="@" + cont['account']['acct'] + ": " + to_out
            m.in_reply_to_id=cont['in_reply_to_id']
        # return m
        # self.update_q.put({'mid': self.mid, 'status': m})
        self.lastbeat=int(time())
        return m

    def process_notification(self, status):
        data=status
        parser = html_parser.MyHTMLParser()
        m=EncodedMessage()
        print("process_notification")
        log("Notification")
        log(str(status))
        m.id=data.get('id')
        m.type=data.get('type')
        to_out=''
        m.from_mid=data['account']['acct']
        if not '@' in m.from_mid:
                m.from_mid=m.from_mid+'@'+self.server_name
        if data['type'] == 'follow':
            to_out = "@{} follows you\n{}".format(
                            data['account']['acct'],
                            data['account']['url'])
        elif data['type'] == 'reblog':
            data['status']['content']=re.sub(r'\n','',data['status']['content'])
            parser.feed(data['status']['content'])
            m.in_reply_to_id=data['status']['in_reply_to_id']
            parser.close()
            text=parser.get_result()
            m.id=data['status']['id']
            m.url=data['status']['url']
            m.visibility=data['status']['visibility']
            to_out = "@{} reblog your status:\n{}".format(
                            data['account']['username'],
                            text)
            media_list = data['status'].get('media_attachments')
            for u in media_list:
                to_out += "\n" + u['url']
        elif data['type'] == 'favourite':
            data['status']['content']=re.sub(r'\n','',data['status']['content'])
            parser.feed(data['status']['content'])
            parser.close()
            m.id=data['status']['id']
            m.url=data['status']['url']
            m.visibility=data['status']['visibility']
            text=parser.get_result()
            to_out = "@{} favourited your status:\n{}".format(
                            data['account']['acct'],
                            text)
            media_list = data['status'].get('media_attachments')
            for u in media_list:
                to_out += "\n" + u['url']
        elif data['type']=='mention':
            data['status']['content']=re.sub(r'\n','',data['status']['content'])
            parser.feed(data['status']['content'])
            parser.close()
            m.id=data['status']['id']
            acct=data['account']['acct']
            m.in_reply_to_id=data['status']['in_reply_to_id']
            if not '@' in acct:
                acct=acct+'@'+self.server_name
            m.add_mentions("@" + acct)
            m.url=data['status']['url']
            m.visibility=data['status']['visibility']
            mentions = data['status']['mentions']
            for a in mentions:
                if not '@' in a['acct']:
                    a['acct']+='@'+self.server_name
                m.add_mentions('@' + a['acct'])
            text=parser.get_result()
            to_out = "@{}:{}".format(
                            data['account']['username'],
                            text)
            media_list = data['status'].get('media_attachments')
            for u in media_list:
                to_out += "\n" + u['url']
        elif data['type'] == 'follow_request':
            to_out = "@{} wants to follow you:\n{}".format(
                            data['account']['acct'],
                            data['account']['url'])
        
        m.text=to_out
        return m
        # self.message_q.put({'mid': self.mid, 'status': m})

    def on_abort(self, error):
        print("ABORT " + self.mid)
        print(error)

    def handle_heartbeat(self):
        print("heartbeat from " + self.mid)
        self.lastbeat=int(time())
        self.got_heartbeat=1 # chack if server sends heartbeats at all
        
        # self.q.put({"mid": self.mid, 'json': {'content': 'beat'}})
        
class MastodonUser:
    def __init__(self, login, access_token):
        if access_token:
            try:
                uname, host = login.split("@")
            except ValueError:
                host=login
            self.mastodon_id=login
            try:
                self.mastodon = Mastodon(
                    access_token=access_token,
                    api_base_url='https://' + host
                )
            except MastodonNetworkError as e:
                print(str(e))
                raise NetworkError()
        self.jids=set()

    def close_listener(self):
        if self.stream:
            # print(type(self.stream))
            self.stream.close()
            self.stream=None
            print("stream for "+self.mastodon_id+" closed")
        
    def update_mid(self, mid):
        self.mastodon_id=mid
    
    def add_jids(self, jids:list):
        self.jids.update(jids)
    
    
    def remove_jid(self,jid):
        try:
            self.jids.remove(jid)
        except:
            pass
    
    def create_listener(self, update_queue=0, notification_queue=0):
        self.listener=MastodonListener(self.mastodon_id)
        self.stream=self.mastodon.stream_user(self.listener,run_async=True, reconnect_async=True)
        print ("added listener for", self.mastodon_id)
        self.listener.jids=self.jids
        self.listener.on_update=self.on_update
        self.listener.on_notification=self.on_notification
        self.listener.lastbeat=int(time())
        if update_queue:
            self.update_q=update_queue
        if notification_queue:
            self.notification_q=notification_queue
        
    def on_update(self, status):
        print("!UPDATE to " + self.mastodon_id + ":")
        # print(status)
        # status_json = json.dumps(status, indent=4, sort_keys=True, default=str)
        m=self.listener.process_update(status)
        self.update_q.put({'mid': self.mastodon_id, 'status': m, 'm':self})
        # mq.putMessage("m:" + self.mid, status_json)
#        def process_update(data: dict, mastodon_id:str) -> dict:
    
    def on_notification(self, status):
        print("!NOTIFICATION to " + self.mastodon_id + ":")
        # print(status)
        # status_json = json.dumps(status, indent=4, sort_keys=True, default=str)
        m=self.listener.process_notification(status)
        self.notification_q.put({'mid': self.mastodon_id, 'status': m, 'm':self})
        # # mq.putMessage("m:" + self.mid, status_json)
        # def process_notification(data:dict, mastodon_id: str) -> str:
        
    def get_thread(self, id):
        mymessages = []
        if id == 0:
            return mymessages
        try:
            toot=self.mastodon.status(id)
            thread = self.mastodon.status_context(id)
            mentions = set()
            start_id = id
        except:
            raise NotFoundError()
            return []
        if len(thread['ancestors']) > 0:
            start_id = thread['ancestors'][0]['id']
            start_message=self.listener.process_update(thread['ancestors'][0])
            for t in thread['ancestors']:
                aa = self.listener.process_update(t)
                mentions.update(aa.mentions)
                aa.add_mentions(mentions)
                mymessages.append(aa)
        mm = self.listener.process_update(toot)
        mentions.update(mm.mentions)
        mm.add_mentions(mentions)
        mymessages.append(mm)
        if len(thread['descendants']) > 0:
            for t in thread['descendants']:
                dd=self.listener.process_update(t)
                mentions.update(dd.mentions)
                dd.add_mentions(mentions)
                mymessages.append(dd)
        return mymessages
    
    def start_register(self, server):
        try:
            (id,secret)=Mastodon.create_app(
                    client_name='mastaj xmpp gateway',
                    api_base_url="https://"+server
                )
            m=Mastodon(
                client_id=id,
                client_secret=secret,
                api_base_url="https://"+server
            )
            url=m.auth_request_url(
                client_id=id,
                scopes=['read','write','follow'],
                redirect_uris='urn:ietf:wg:oauth:2.0:oob'
            )
            self.mastodon=m
            self.mastodon_id=server
            print(url)
            return url
        except MastodonNetworkError:
            raise NetworkError()
        
    
    def finish_register(self, token):
        if not self.mastodon:
            self.start_register(self.mastodon_id)
        try:
            act=self.mastodon.log_in(
                    code=token,
                    scopes=['read','write','follow'],
                    redirect_uri='urn:ietf:wg:oauth:2.0:oob'
                )
            print("finish register returns",act)
            return act
        except (MastodonUnauthorizedError, MastodonIllegalArgumentError) as e:
            print(e)
            return 0
        
    def verify_account(self):
        try:
            res=self.mastodon.account_verify_credentials()
            if not self.mastodon_id:
                self.mastodon_id=res['acct']
            return res
        except MastodonUnauthorizedError as e:
            print(str(e))
            return 0
    
    def check_timeout(self):
        t = int(time())
        if not self.listener.got_heartbeat:
            return 0
        if t - self.listener.lastbeat > TIMEOUT:
            print("\n" + self.mastodon_id + " timeout")
            return 1
        
        return 0
            
        
    
    # def auth_request_url(self):
    #     return self.mastodon.auth_request_url(
    #         client_id='Jabber gateway',
    #         redirect_uris='urn:ietf:wg:oauth:2.0:oob',
    #         scopes=['read', 'write', 'follow'],
    #         force_login=False)
    
    def status_reblog(self, id):
        try:
            res=self.mastodon.status_reblog(id)
            return self.listener.process_update(res)
        except MastodonNotFoundError:
            raise NotFoundError()
    
    def status_favourite(self, id):
        try:
            res=self.mastodon.status_favourite(id)
            res=self.listener.process_update(res)
            res.text="Favourited:\n" + res.text
            return res
        except MastodonNotFoundError:
            raise NotFoundError()
    
    def get_status(self, id):
        try:
            res=self.mastodon.status(id)
            return self.listener.process_update(res)
        except MastodonNotFoundError:
            raise NotFoundError()
    
    def status_post(self, status, visibility='public', in_reply_to_id=None):
        try:
            res=self.mastodon.status_post(
                status=status,
                in_reply_to_id=in_reply_to_id,
                visibility=visibility
            )
            return res
        except MastodonAPIError as e:
            print("API Error:",str(e))
            raise APIError(e)
        except MastodonNotFoundError:
            print("NotFoundError")
            raise NotFoundError()
            
            
            
    
