# Mastodon <-> XMPP gate

It allows use your mastodon account via XMPP client (for example Conversations).

Currently for test you can add to your roster contact **mastodon.xmmg.ru** (yes, without @, it's a service, not a regular contact)

After you asked authorization from mastodon.xmmg.ru, you'll see an auth request from config@mastodon.xmmg.ru. Also it will send you a short description how to configure the gate.

All work woth the gate is separated to 4 different roster contacts.

1. config@mastodon.xmmg.ru

    It's used to configure and bind a mastodon account

    ##### Possible commands:
    *server <server>* - bind mastodon account. After that you should paste an mastodon authorization token   
    *enable* or *e* - enable message delivery   
    *disable* or *d* - disable message delivery   
    *info* - info about bound mastodon account   

2. new@mastodon.xmmg.ru

    For new posts. All text you send here will be posted in mastodon


3. home@mastodon.xmmg.ru

    Home feed. All mastodon massages from your subscriptions will be here
    ##### Available commands:
    *.* - open last message in a separate chat  
    *.1* - open a first before last message in a separate chat  
    *.2* - open secondary before last message in a separate chat  
    etc. up to 99-th message
    
    *r* - reblog last message  
    *r1* - reblog a first before last message  
    *r2* - open secondary before last message  
    etc. up to 99-th message
    
    *w* - get www link to last message
    
    Also, instead of pointing desired message by index, you can use a quotation. To reblog desired message you can use the following (standard qutation option in Conversations):
    
    ##### Sample:
        > @test@mastodon.tld:
        > original message
        r
    to reblog message from @test@mastodon.tld with text 'original message'
    
    It's impossible to answer to message in this chat. To answer the message you should open a thread in a separate chat with . (dot) command

4. Contacts that looks like [long number]@mastodon.xmmg.ru

    It's a threads.
    All you write here will be posted to the thread as an answer to last message.
    No need to add mentions, the gate will do it by itself
    
    ##### Available commands for the chat:
    *.* - get full thread   
    *w* - get www link to the thread   


### Questions?
xmpp:shura0@yax.im
