#!/usr/bin/env python3

import unittest
import sys

# sys.path.append('./venv/lib/python3.7/site-packages')
sys.path.append('../venv/lib/python3.7/site-packages')
sys.path.append('../')

import mastodon_listener
from message_store import MessageStore
import gxmpp
import html_parser
from queue import Empty, Queue
import json
import db
import time
from shutil import copyfile
import main


UPDATES_FILE = 'mastodon_update.json'
NOTIFICATIONS_FILE = 'mastodon_notification.json'

UPDATES_RSULT_FILE = 'mastodon_updates.txt'
NOTICICATIONS_RESULT_FILE = 'mastodon_notifications.txt'

MASTODON_ID='shura@mastodon.social'
USERS_TEST_DB='users_test.db'
MESSAGES_TEST_DB='test_messages.db'

class TestAll(unittest.TestCase):
    def test_update(self):
        """
        Test for mastodon update processing
        """
        with open(UPDATES_FILE) as f:
            data=f.read()
        f.close()
        j = json.loads(data)
        q = Queue()
        m=mastodon_listener.MastodonListener(MASTODON_ID)
        if type(j) is list:
            for i in j:
                m.on_update(i)
        else:
            m.on_update(j)

        with open(UPDATES_RSULT_FILE) as f:
            data=f.read()
        ju=json.loads(data)
        f.close()
        while not q.empty():
            m=q.get()
            u=ju.pop(0)
            em=mastodon_listener.EncodedMessage()
            em.text=u['text']
            em.id=u['id']
            em.url=u['url']
            em.visibility=u['visibility']
            em.add_mentions(u['mentions'])
            ment=em.mentions
            em.add_mentions({'set'})
            self.assertEqual(m['status'].to_dict(), em.to_dict())
        
    def test_notification(self):
        with open(NOTIFICATIONS_FILE) as f:
            data=f.read()
        f.close()
        j = json.loads(data)
        q = Queue()
        m=mastodon_listener.MastodonListener(MASTODON_ID)
        if type(j) is list:
            for i in j:
                m.on_notification(i)
        else:
            m.on_notification(j)

        with open(NOTICICATIONS_RESULT_FILE) as f:
            u=f.read()
        ju=json.loads(u)
        f.close()
        while not q.empty():
            m=q.get()
            u=ju.pop(0)
            em=mastodon_listener.EncodedMessage()
            em.text=u['text']
            em.id=u['id']
            em.url=u['url']
            em.visibility=u['visibility']
            em.add_mentions(u['mentions'])
            self.assertEqual(m['status'].to_dict(), em.to_dict())

    def test_users(self):
        tmp_db=USERS_TEST_DB+'.bak'
        copyfile(USERS_TEST_DB, tmp_db)
        database = db.Db(tmp_db)
        users=database.get_users()
        self.assertEqual(len(users),3)
        mu=main.get_uniq_mids(users)
        emu={
            'shura@mastodon.social': {
                'token': '53c6c387a730b42586042ceb69e2e6581ca4602ba406f758cf71019ff8ce9b71',
                'jids': ['admin@lenovo.myhome', 'admin@home.myhome']},
             'onemore@masto.test': {
                'token': '111',
                'jids': ['user2@home.myhome']}
             }
        print(mu)
        self.assertEqual(mu,emu)
        
        database.add_user('test@jid','test@mid', '')
        database.set_status_by_jid('test@jid','enabled')
        users=database.get_users()
        mu={}
        for u in users:
            if not mu.get(u['mid']):
                mu[u['mid']]=list([u['jid']])
            else:
                mu[u['mid']].append(u['jid'])
        print(mu)
        emu={
            'onemore@masto.test': ['user2@home.myhome'],
            'shura@mastodon.social': ['admin@lenovo.myhome', 'admin@home.myhome'],
            'test@mid':['test@jid']
            }
        self.assertEqual(mu,emu)
        user=database.get_user_by_jid('user2@home.myhome')
        sample={'jid': 'user2@home.myhome', 'status': 'enabled', 'token': '111', 'mid': 'onemore@masto.test'}
        self.assertEqual(user,sample)
        user=database.get_user_by_jid('non-exist')
        self.assertEqual(user,None)
        masto_users=[]
        # for u in users:
        #     _=mastodon_listener.MastodonUser(u['mid'],u['token'])
        #     _.add_jids(mu[u['mid']])
        #     masto_users.append(_)
        # time.sleep(5)

    def test_messages(self):
        tmp_db=MESSAGES_TEST_DB+'.bak'
        copyfile(MESSAGES_TEST_DB, tmp_db)
        message_store=MessageStore(tmp_db)
        mentions=set(['@test@mastodon.social'])
        id=104032314153599025
        message_store.update_mentions(id, mentions)
        toot=message_store.get_message_by_id(id)
        sample=set(['@test@mastodon.social','@groosha@mastodon.ml'])
        self.assertEqual(set(toot['mentions'].split(' ')),sample)
        mentions=set(['@test@mastodon.social', '@test2@mastodon.social'])
        message_store.update_mentions(id, mentions)
        toot=message_store.get_message_by_id(id)
        sample.update(['@test2@mastodon.social'])
        self.assertEqual(set(toot['mentions'].split(' ')),sample)
        
        search_for='''@inhosin@mastodon.ml:
Захотелось прочитать книгу по Linux. А то юзаю как чайник.'''
        toot=message_store.find_message(search_for)
        # print(toot)
        self.assertEqual(toot['id'],'104032564439980906')
        search_for='''@sptnkmmnt@mastodon.ml:
Когда-то очень давно, я записывал концерт Spititual Front на айпад.  
В смысле, стоял в зале и снимал.  
Сейчас понимаю, как тупо я выглядел.  
И меня мучает вопрос:
Интересно, а как музыкантов не бесит, что вместо того, чтобы наслаждаться музыкой, текстами, там... шоу, в конце концов, народ утыкается в смарты и просто "ксерокопирует" форму без содержания?
'''
        toot=message_store.find_message(search_for)
        self.assertEqual(toot['id'],'104032809534204360')
        
        search_for='''@Vladimir_Vladimirovich:
Судно "Академик Черский", способное достроить "Северный поток-2", которое по данным независимых СМИ шло в Находку, внезапно оказалось у берегов Дании. Наверное решили идти в Находку Северным морским путём.'''
        toot=message_store.find_message(search_for)
        self.assertEqual(toot,None)
    
    def test_xmpp_users(self):
        tmp_db=USERS_TEST_DB+'.bak'
        copyfile(USERS_TEST_DB, tmp_db)
        database = db.Db(tmp_db)
        users=database.get_users()
        xmpp=gxmpp.Component('megagate.home.myhome', '123456', 'localhost', 5347)
        xmpp.register_plugin('xep_0030')  # Service Discovery
        xmpp.register_plugin('xep_0004')  # Data Forms
        xmpp.register_plugin('xep_0060')  # PubSub
        xmpp.register_plugin('xep_0199')  # XMPP Ping
        xmpp.add_users(users)
        self.assertEqual(users, xmpp.users)

    def test_html_parser(self):
        html='''<p>Катали с приятелем в двухдневный поход на выходных.
        Наснимал немножко видео и попробовал немножко помонтировать. Прошу смотреть и оценивать.<br>
        День первый: <a href="https://www.youtube.com/watch?v=Rma0SafnztU" rel="nofollow noopener noreferrer" target="_blank">youtube.com</a></p>
        <a href="https://juick.com/tag/%D0%B2%D0%B5%D0%BB%D0%BE" rel="nofollow noopener noreferrer" target="_blank">#вело</a>
        <a href="https://juick.com/tag/bike" rel="nofollow noopener noreferrer" target="_blank">#bike</a>

'''
        p=html_parser.MyHTMLParser()
        p.feed(html)
        p.close()
        text=p.get_result()
        print("HTML parser text:'"+ text+"'")
        sample_text='''
Катали с приятелем в двухдневный поход на выходных.        Наснимал немножко видео и попробовал немножко помонтировать. Прошу смотреть и оценивать.
        День первый: https://www.youtube.com/watch?v=Rma0SafnztU        #вело        #bike'''
        print("HTML parser sample:'"+ sample_text + "'")
        self.assertEqual(text, sample_text)
        
        html='''<p>Сегодня снова колесил <a href="https://mastodon.host/tags/%D0%BF%D0%BE%D0%BB%D1%81%D1%82%D0%B0" class="mention hashtag
" rel="nofollow noopener noreferrer" target="_blank">#<span>полста</span></a>. Дежурный маршрут: после дождей другое слиш
ком рисковано.</p><p>Наконец начал методично работать над силой: только первый тягун преодолел на 22:28, а остальные — то
лько на повышающих передачах (минимум 1,05).</p><p>Несмотря на обилие <a href="https://mastodon.host/tags/%D1%84%D0%BE%D1
%82%D0%BE" class="mention hashtag" rel="nofollow noopener noreferrer" target="_blank">#<span>фото</span></a> остановок, с
редний темп более 22 км/ч.</p><p>Фото в комментариях.</p><p><span class="h-card"><a href="https://mastodon.ml/@rf" class=
"u-url mention" rel="nofollow noopener noreferrer" target="_blank">@<span>rf</span></a></span> <span class="h-card"><a hr
ef="https://mastodon.social/@russian_mastodon" class="u-url mention" rel="nofollow noopener noreferrer" target="_blank">@
<span>russian_mastodon</span></a></span></p>
'''
        sample_text='''
Сегодня снова колесил  #полста. Дежурный маршрут: после дождей другое слишком рисковано.
Наконец начал методично работать над силой: только первый тягун преодолел на 22:28, а остальные — только на повышающих передачах (минимум 1,05).
Несмотря на обилие  #фото остановок, средний темп более 22 км/ч.
Фото в комментариях.
@rf @russian_mastodon'''
        p=html_parser.MyHTMLParser()
        p.feed(html)
        p.close()
        text=p.get_result()
        # print(text)
        self.assertEqual(text, sample_text)
        html='<p>Я несколько лет не посещал этот сайт, с удивлением обнаружил, что он всё ещё жив и даже пополнился новыми фичами:</p><p>«Российский дзен. Бессмысленный и беспощадный».<br><a href="https://zenrus.ru/" rel="nofollow noopener noreferrer" target="_blank"><span class="invisible">https://</span><span class="">zenrus.ru/</span><span class="invisible"></span></a></p>'
        sample_text='''
Я несколько лет не посещал этот сайт, с удивлением обнаружил, что он всё ещё жив и даже пополнился новыми фичами:
«Российский дзен. Бессмысленный и беспощадный».
https://zenrus.ru/'''
        p=html_parser.MyHTMLParser()
        p.feed(html)
        p.close()
        text=p.get_result()
        # print(text)
        self.assertEqual(text, sample_text)
        html='@<span class=""><a href="https://mastodon.host/users/velociraptor" class="u-url mention" rel="nofollow noopener noreferrer" target="_blank"><span class="mention">velociraptor</span></a></span> ИМХО зря покрасили, лубок получился. Или это всегда так было?'
        sample_text='@velociraptor ИМХО зря покрасили, лубок получился. Или это всегда так было?'
        p=html_parser.MyHTMLParser()
        p.feed(html)
        p.close()
        text=p.get_result()
        # print(text)
        self.assertEqual(text, sample_text)
        html='''Отдыхаете? Карантините помаленьку?<br><br>А мы пашем!!!<br><br>#<a href="https://friends.deko.cloud/search?tag=%D0%A2%D0%B0%D0%BA%D0%B8%D0%B5%D0%94%D0%B5%D0%BB%D0%B0" class="" rel="nofollow noopener noreferrer" target="_blank">ТакиеДела</a>
<p><span class="h-card"><a href="https://friends.deko.cloud/profile/shuro" class="u-url mention" rel="nofollow noopener noreferrer" target="_blank">@<span>shuro</span></a></span> Жму руку.</p>'''
        sample_text='''Отдыхаете? Карантините помаленьку?

А мы пашем!!!

#ТакиеДела
@shuro Жму руку.'''
        p=html_parser.MyHTMLParser()
        p.feed(html)
        p.close()
        text=p.get_result()
        # print(text)
        self.assertEqual(text, sample_text)

        html='''<p>Будет что послушать, иначе Aleckat &amp; Hynamo затеру до дыр. \n<a href="https://sound.skrep.in/library/albums/4" rel="nofollow noopener noreferrer" target="_blank"></a><a href="https://sound.skrep.in/library/albums/4" rel="nofollow noopener noreferrer" target="_blank">https://sound.skrep.in/library/albums/4</a>/</p>'''
        sample_text='''
Будет что послушать, иначе Aleckat & Hynamo затеру до дыр. https://sound.skrep.in/library/albums/4/'''
        p=html_parser.MyHTMLParser()
        p.feed(html)
        p.close()
        text=p.get_result()
        print("HTML parser text:'"+ text+"'")
        # print(text)
        self.assertEqual(text, sample_text)


if __name__ == '__main__':
    unittest.main()
