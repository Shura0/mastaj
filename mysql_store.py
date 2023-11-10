#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import mysql.connector
# import time
# from datetime import datetime
from mysql.connector import errorcode
# import re


class MessageStore:
    def __init__(self, host, port, database, username, password):
        self.host = host
        self.db = None
        if host:
            self.connect(host, port, database, username, password)

    def __del__(self):
        if self.db:
            self.db.close()

    def connect(self, host, port, database, username, password):
        self.host = host
        self.port = port
        self.database = database
        self.username = username

        try:
            self.db = mysql.connector.connect(
                host=host,
                port=port,
                database=database,
                user=username,
                password=password)
        except mysql.connector.Error as err:
            print("Error code =" + str(err.errno))
            print(err)
            # time.sleep(1)
            if err.errno == errorcode.ER_BAD_DB_ERROR:
                "Database is not exist. Trying to create"
                try:
                    self.db = mysql.connector.connect(
                        host=host,
                        port=port,
                        user=username,
                        password=password)
                    self.cursor = self.db.cursor(dictionary=True, buffered=True)
                    self.cursor.execute(
                        "CREATE DATABASE {} DEFAULT CHARACTER SET 'utf8mb4' COLLATE  utf8mb4_unicode_ci".format(self.database))
                    print("database created")
                    self.cursor.execute('USE {}'.format(self.database))
                except mysql.connector.Error as err:
                    print("Failed creating database: {}".format(err))
                    exit(1)
            else:
                exit(1)
        except Exception as e:
            print("Cannot connect to database")
            print(e)
            exit(1)

        self.cursor = self.db.cursor(dictionary=True, buffered=True)
        self.cursor.execute(
            "SELECT table_name FROM information_schema.TABLES WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_NAME='Messages'")
        res = self.cursor.fetchall()
        print(res)
        self.cursor.execute('set names utf8mb4')
        if not res:
            print("Messages db is not exist.\nCreating...", end=' ')
            try:
                self.cursor.execute('''
                    CREATE TABLE `Messages` (
                        `date` DATETIME NOT NULL,
                        `mentions` TEXT,
                        `url` VARCHAR(128) NOT NULL,
                        `message` TEXT,
                        `visibility` VARCHAR(16) NOT NULL,
                        `id` VARCHAR(32) NOT NULL,
                        `mid` VARCHAR(64) NOT NULL,
                        `feed` VARCHAR(32) NOT NULL,
                        KEY(`id`)
                    ) ENGINE = InnoDB
                ''')
                self.cursor.execute('''
                    CREATE INDEX `feed` ON Messages (feed)
                ''')
                self.cursor.execute('''
                    CREATE INDEX `date` ON Messages (date)
                ''')
                self.cursor.execute('''
                    CREATE INDEX `message` ON Messages (message)
                ''')
                self.cursor.execute('set names utf8mb4')
            except Exception as e:
                print("Cannot create message table")
                print(e)
                exit(1)
        self.cursor.close()

    def add_message(self, message, url, author, mentions, visibility, id, mid, date, feed='home'):
        try:
            if not author.startswith('@'):
                author = '@' + author
            mentions.remove(author)
        except (ValueError, KeyError):
            pass
        mentions_str = (" ".join(mentions)).strip()
        if mentions_str:
            mentions_str = author + ' ' + mentions_str
        else:
            mentions_str = author
        # mentions_str = author + ' ' + mentions_str
        print("going to add message: " + message)
        sql = "SELECT id from Messages WHERE id=%s AND mid=%s AND feed=%s LIMIT 1"
        data = (str(id), mid, str(feed))
        try:
            cursor = self.db.cursor(dictionary=True)
            cursor.execute(sql, data)
            res = cursor.fetchone()
            if res:
                print("Already added")
                return None
            sql = "INSERT INTO Messages (date, url, mentions, message, visibility, id, mid, feed) VALUES (FROM_UNIXTIME(%s), %s, %s, %s, %s, %s, %s, %s);"
            d = date.timestamp()
            params = (
                d,
                url,
                mentions_str,
                message.encode(),
                visibility,
                str(id),
                mid,
                str(feed))
            cursor.execute(sql, params)
            self.db.commit()
            cursor.close()
            print("commit success")
        except Exception as e:
            print("Handled error : ")
            print(e)

    def find_message(self, text, mid, feed='home'):
        # text=re.sub(r'([^"])"',r'\1""',text)
        # text = re.sub(r'"', r'""', text)
        print("Search for '" + text + "'")
        text = ("%" + text + "%")
        sql = "SELECT * FROM Messages WHERE message LIKE %s AND mid = %s AND feed = %s ORDER BY date DESC LIMIT 1"
        print("SELECT * FROM Messages WHERE message LIKE {} AND mid = {} AND feed = {} ORDER BY date DESC LIMIT 1".format(text, str(mid), str(feed)))
        cursor = self.db.cursor(dictionary=True)
        cursor.execute(sql, (text, str(mid), str(feed)))
        res = cursor.fetchone()
        cursor.close()
        return res

    def get_message_by_id(self, id: str):
        sql = "SELECT * FROM Messages WHERE id = %s LIMIT 1"
        cursor = self.db.cursor(dictionary=True, buffered=True)
        cursor.execute(sql, [str(id)])
        a = cursor.fetchone()
        print("get_message_by_id")
        print(a)
        print("==")
        cursor.close()
        return a

    def get_messages_for_user(self, mid):
        sql = "SELECT id FROM Messages WHERE mid=%s AND feed=%s ORDER BY date DESC"
        cursor = self.db.cursor(dictionary=True, buffered=True)
        cursor.execute(sql, (mid, 'home'))
        a = cursor.fetchall()
        cursor.close()
        return [i['id'] for i in a]

    def get_messages_for_user_by_thread(self, mid, feed):
        sql = "SELECT id FROM Messages WHERE mid=%s AND feed=%s ORDER BY date DESC"
        print("MYSQL get_messages_for_user_by_thread")
        print("SELECT id FROM Messages WHERE mid={} AND feed={} ORDER BY date DESC".format(str(mid), str(feed)))
        cursor = self.db.cursor(dictionary=True, buffered=True)
        cursor.execute(sql, (mid, str(feed)))
        a = cursor.fetchall()
        cursor.close()
        return [i['id'] for i in a]

    def del_messages_by_mid(self, mid):
        cursor = self.db.cursor(dictionary=True, buffered=True)
        cursor.execute("DELETE FROM Messages WHERE mid= %s", (mid,))
        self.db.commit()
        cursor.close()

    def drop_database(self):
        cursor = self.db.cursor(dictionary=True, buffered=True)
        cursor.execute("DROP DATABASE %s" % (self.database))
        cursor.close()
