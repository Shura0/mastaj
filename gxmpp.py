from slixmpp.componentxmpp import ComponentXMPP
import re


class Component(ComponentXMPP):

    def __init__(self, jid, secret, server, port):
        ComponentXMPP.__init__(self, jid, secret, server, port)

        self.add_event_handler("message", self.message)
        self.index = 0
        self.users = []
        self.jid = jid
        self.my_contacts = [
            'new',
            'config',
            'home'
        ]

    def add_users(self, users: list):
        self.users += users

    def attach_queue(self, q):
        self.queue = q

    def message(self, msg):
        if msg.get('type') == 'error':
            return
        body = msg.get('body')
        print("Got message '" + body + "' from " + str(msg.get('from')))
        jid = re.sub(r'/.+$', '', str(msg['from']))
        to = re.sub(r'/.+$', '', str(msg['to']))
        self.queue.put({'jid': jid, 'body': body, 'to': to})

    def send_online(self, jid):
        self.send_presence(pfrom=self.jid,
                           pto=jid,
                           ppriority=1)
        for j in self.my_contacts:
            self.send_presence(pfrom=j + '@' + self.jid,
                               pto=jid,
                               ppriority=1)

    def send_offline(self, admin_jid):
        self.send_presence(ptype='unavailable',
                           pfrom=self.jid,
                           pto=admin_jid)
        for j in self.my_contacts:
            self.send_presence(pfrom=j + '@' + self.jid,
                               ptype='unavailable',
                               pto=admin_jid)

    def _handle_session_start(self, event):
        print("Session started")
        for u in self.users:
            self.send_online(u['jid'])

    def _handle_presence(self, presence):
        print('presense from', presence['from'])
        jid = re.sub(r'/.+$', '', str(presence['from']))
        to = re.sub(r'/.+$', '', str(presence['to']))
        print(presence['type'])
        if presence['type'] == 'probe':
            self.send_presence(pfrom=presence['to'],
                               pto=presence['from'],
                               ppriority=1)
        elif presence['type'] == 'subscribe':
            self.send_presence(pto=presence.get('from'),
                               pfrom=presence['to'],
                               ptype='subscribed')
            self.send_presence(pfrom=presence['to'],
                               pto=presence.get('from'),
                               ppriority=1)
            if to == self.jid:  # Subscription to service
                self.send_message(
                    presence.get('from'),
                    "Please add this contact to your roster. The contact is for managing your mastodon account\n" +
                    "Type 'help' for help\n" +
                    "Please enter your mastodon server name with command 'server'. For example:\n" +
                    'server mastodon.social',
                    mfrom="config@" + self.jid,
                    mtype='chat')
                self.send_presence(pto=presence.get('from'),
                                   pfrom='config@' + self.jid,
                                   ptype='subscribe')
                self.send_presence(pfrom='config@' + self.jid,
                                   pto=presence.get('from'),
                                   ppriority=1)

        elif presence['type'] == 'subscribed':
            self.send_presence(pfrom=presence['to'],
                               pto=presence.get('from'),
                               ppriority=1)
        elif presence['type'] == 'unsubscribe' or presence['type'] == 'unsubscribed':
            print("to:", to)
            print("from:", jid)
            print("self.jid:", self.jid)
            if to == self.jid:  # unsubscribed from service
                self.queue.put({'jid': jid,
                                'body': None,
                                'to': to,
                                'command': "unsubscribe"})
                for j in self.my_contacts:
                    print("unsubscribed from ", j + '@' + self.jid)
                    self.send_presence(pto=presence.get('from'),
                                       pfrom=j + '@' + self.jid,
                                       ptype='unsubscribe')
                    self.send_presence(pto=presence.get('from'),
                                       pfrom=j + '@' + self.jid,
                                       ptype='unsubscribed')
        elif presence['type'] == 'error':
            print(presence)

    def register_new_user(self, jid):
        for j in self.my_contacts:
            self.send_presence(pto=jid,
                               pfrom=j + '@' + self.jid,
                               ptype='subscribe')
            self.send_presence(pfrom=j + '@' + self.jid,
                               pto=jid,
                               ppriority=1)
        self.send_message(
            jid,
            "Please add this contact to your roster. Write here to make new post",
            'For new posts',
            mfrom="new@" + self.jid,
            mtype='chat')
        self.send_message(
            jid,
            "Please add this contact to your roster. You will receive here your home feed",
            'Your home feed',
            mfrom="home@" + self.jid,
            mtype='chat')

    def _connection_failed(self, err):
        if err:
            print(err)
