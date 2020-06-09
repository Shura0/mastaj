# -*- coding: utf-8 -*-

import sqlite3


def dict_factory(cursor: object, row: object) -> object:
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


class Db:
    def __init__(self, filename):
        self.filename = filename
        if filename:
            self.connect(filename)

    def connect(self,filename=''):
        if filename:
            self.filename=filename

        if self.filename == '':
            return 0
        self.db=sqlite3.connect(self.filename)
        self.db.row_factory= dict_factory
        self.cursor=self.db.cursor()
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Users'")
        res=self.cursor.fetchall()
        if not res:
            self.cursor.execute('''CREATE TABLE 'Users'(
                        `jid` TEXT NOT NULL PRIMARY KEY,
                        `mid` TEXT NOT NULL,
                        `token` TEXT NOT NULL,
                        `status`)''');
            self.db.commit()

    def get_user_by_jid(self,jid):
        self.cursor.execute('SELECT * FROM "Users" WHERE jid = (?)', [jid])
        res=self.cursor.fetchone()
        return res

    def getUsersByMid(self,mid):
        self.cursor.execute("SELECT * FROM 'Users' WHERE mid = (?) AND status != 'disabled'", [mid])
        res=self.cursor.fetchall()
        return res

    def get_users(self):
        self.cursor.execute("SELECT * FROM 'Users' WHERE status != 'disabled' AND status != 'registration'")
        return self.cursor.fetchall()

    def getTags(self):
        self.cursor.execute("SELECT tag FROM 'Tags'")
        #todo: add uniq
        return self.cursor.fetchall()

    def getSubscribersByTag(self, tag):
        self.cursor.execute("SELECT * FROM Users INNER JOIN Tags USING (jid) WHERE Tags.tag = (?)",[tag,])
        return self.cursor.fetchall()

    def getTagsByJid(self, jid):
        self.cursor.execute("SELECT tag FROM 'Tags' WHERE jid = (?)",[jid])
        return self.cursor.fetchall

    def add_user(self, jid, mid, token):
        self.cursor.execute("SELECT jid FROM 'Users' WHERE jid = (?)",[jid])
        res=self.cursor.fetchall()
        if len(res) > 0:
            print ("User is exist. Update base...")
            res=self.cursor.execute("UPDATE 'Users' SET 'mid'=(?), 'token'=(?) WHERE jid = (?)",(mid,token,jid))
            self.db.commit()
            if res:
                print ("OK\n")
                return 1
            else:
                return 0
        res=self.cursor.execute("INSERT INTO 'Users' (jid, mid, token, status) VALUES (?,?,?,'registration')",(jid,mid,token))
        self.db.commit()

    def addTagToJid(self,tag,jid):
        self.cursor.execute("SELECT jid FROM 'Tags' WHERE tag = (?) AND jid = (?)",(tag,jid))
        res=self.cursor.fetchall()
        if len(res) < 1:
            self.cursor.execute("INSERT INTO 'Tags' (jid, tag) VALUES ( ?, ? )",(jid,tag))
            self.db.commit()
        print("user: "+jid+" subscribed to #"+tag)

    def set_status_by_jid(self, jid, status):
        self.cursor.execute("UPDATE 'Users' SET `status`=(?) WHERE jid = (?)", (status, jid))
        self.db.commit()
    
    def set_mid_by_jid(self, jid, mid):
        self.cursor.execute("UPDATE 'Users' SET `mid`=(?) WHERE jid = (?)", (mid, jid))
        self.db.commit()
    
    def set_token_by_jid(self, jid, token):
        self.cursor.execute("UPDATE 'Users' SET `token`=(?) WHERE jid = (?)", (token, jid))
        self.db.commit()

    def del_user_by_jid(self, jid):
        self.cursor.execute("DELETE FROM 'Users' WHERE jid = (?)",[jid])
        self.db.commit()

    def delUserByMid(self, mid):
        self.cursor.execute("DELETE FROM 'Users' WHERE mid= (?)", [mid])
        self.db.commit()

    def delTagByJid(self, tag, jid):
        self.cursor.execute("DELETE FROM 'Tags' WHERE jid = (?) AND tag = (?)",(jid,tag))
        self.db.commit()

    def addAutoboostToJid(self, mid, jid):
        mid=mid.lower()
        jid=jid.lower()
        self.cursor.execute("SELECT jid FROM 'Autoboost' WHERE mid = (?) AND jid = (?)",(mid,jid))
        res=self.cursor.fetchall()
        if len(res) < 1:
            self.cursor.execute("INSERT INTO 'Autoboost' (jid, mid) VALUES ( ?, ? )",(jid,mid))
            self.db.commit()
        print("user "+mid+" added to autoboost")

    def delAutoboostByJid(self, mid, jid):
        mid=mid.lower()
        jid=jid.lower()
        self.cursor.execute("DELETE FROM 'Autoboost' WHERE jid = (?) AND mid = (?)",(jid,mid))
        self.db.commit()

    def getAutoboostByJid(self, jid):
        jid=jid.lower()
        self.cursor.execute("SELECT * FROM 'Autoboost' WHERE jid = (?)",[jid])
        return self.cursor.fetchall()

    def getAutoboostByJidMid(self, jid,mid):
        mid=mid.lower()
        jid=jid.lower()
        self.cursor.execute("SELECT * FROM 'Autoboost' WHERE mid = (?) AND jid = (?)",(mid,jid))
        a=self.cursor.fetchall()
        if a and a[0]: return a[0]
        return None

