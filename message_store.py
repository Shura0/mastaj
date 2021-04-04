#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import sqlite3
from datetime import datetime
import re

def dict_factory(cursor: object, row: object) -> object:
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


class MessageStore:
    def __init__(self, filename):
        self.filename = filename
        if filename:
            self.connect(filename)

    def connect(self, filename=''):
        if filename:
            self.filename = filename

        if self.filename == '':
            return 0
        self.db = sqlite3.connect(self.filename)
        self.db.row_factory = dict_factory
        self.cursor = self.db.cursor()
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Messages'")
        res = self.cursor.fetchall()
        print(res)
        if not res:
            print("Messages db is not exist.\nCreating...", end=' ')
            self.cursor.execute("CREATE VIRTUAL TABLE 'Messages' USING FTS5(" +
                                "`date`, `mentions`,`url`, `message`, `visibility`, `id`, `mid`, 'feed')");
            a = self.cursor.fetchall()
            if a:
                print('ok')

    def add_message(self, message, url, mentions, visibility, id, mid, feed='home', date=0):
        mentions_str=" ".join(mentions)
        sql = "SELECT id from 'Messages' WHERE id=? AND mid=?"
        print(id,mid)
        res=self.cursor.execute(sql,[id,mid])
        res = self.cursor.fetchall()
        print("CURSOR")
        print(res)
        if res:
            return None
        sql = "INSERT INTO 'Messages' (date, url, mentions, message, visibility, id, mid, feed) VALUES (?, ?, ?, ?, ?, ?, ?, ?);"
        d = int(datetime.today().timestamp())
        if date:
            d = date
        params=(d,
                url,
                mentions_str,
                message,
                visibility,
                str(id),
                mid,
                feed)
        print(params)
        res=self.cursor.execute(sql,
                            params
                            )
        print(res)
        self.db.commit()
        return res
    
    def find_message(self, text, mid, feed='home'):
        text=re.sub(r'([^"])"',r'\1""',text)
        text='message:"'+text+'" mid:"' + str(mid) + '" feed:"' + str(feed) + '"'
        sql="SELECT * FROM 'Messages' WHERE Messages MATCH (?) ORDER BY 'date' DESC";
        res=self.cursor.execute(sql,[text])
        a=self.cursor.fetchall()
        if a:
            return a[-1]
        return None

    def update_mentions(self, id, mentions):
        sql="SELECT mentions FROM 'Messages' WHERE id =(?)"
        self.cursor.execute(sql,(str(id),))
        m=self.cursor.fetchone()
        
        if m:
            m=m.get('mentions')
            mset=set(m.split(' '))
            mset.update(mentions)
        else:
            mset=mentions
        
        mentions_str = " ".join(mset)
        sql="UPDATE 'Messages' SET mentions = (?) WHERE id =(?)"
        self.cursor.execute(sql,[mentions_str,str(id)])
        self.db.commit()

    def get_message_by_id(self, id: str):
        sql="SELECT * FROM 'Messages' WHERE id = (?)"
        self.cursor.execute(sql, [str(id)])
        return self.cursor.fetchone();
    
    def get_messages_for_user(self, mid):
        sql="SELECT id FROM 'Messages' WHERE mid=(?) AND feed=(?) ORDER BY date DESC";
        self.cursor.execute(sql, (mid,'home'))
        a=self.cursor.fetchall()
        return [i['id'] for i in a]
    
    def get_messages_for_user_by_thread(self, mid, thread):
        sql="SELECT id FROM 'Messages' WHERE mid=(?) AND feed=(?) ORDER BY date DESC";
        self.cursor.execute(sql, (mid, str(thread)))
        a=self.cursor.fetchall()
        return [i['id'] for i in a]
    
    
    def del_messages_by_mid(self, mid):
        self.cursor.execute("DELETE FROM 'Messages' WHERE mid= (?)", [mid])
        self.db.commit()
    
