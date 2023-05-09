from html.parser import HTMLParser
import re


# create a subclass and override the handler methods
class MyHTMLParser(HTMLParser):
    def __init__(self):
        self.OFF = 0
        self.OUT = ''
        self.inside_link = 0
        self.link_text = ''
        self.mention = 0
        self.last_char = ''
        HTMLParser.__init__(self)

    def handle_starttag(self, tag, attrs):
        if self.OFF:
            return
        # print("handle_starttag "+ tag)
        link = ''
        if tag == "a":
            for i in attrs:
                if i[0] == 'href':
                    link = i[1]
            # import ipdb; ipdb.set_trace()
            self.inside_link = link
            self.link = link
            self.link_text = ''
            flag = 0
            for attr in attrs:
                if attr[0] == 'style' or attr[0] == 'id' or attr[0] == 'class':
                    if attr[0] == 'class' and 'mention' in attr[1]:
                        self.mention = 1
                    flag = 1
            if not flag:
                # self.OUT += link + ' '
                # self.OFF=1
                pass
        elif tag == 'br' or tag == 'p':
            self.OUT += "\n"
        if tag == 'p':
            for attr in attrs:
                if attr[0] == 'id' and attr[1] == 'toolbar':
                    self.OFF = 1
                    break

    def handle_endtag(self, tag):

        # print('handle_endtag '+ tag)
        if tag == 'a':
            if self.link_text:
                self.OUT += self.link_text
                self.link_text = ''
                self.mention = 0
            elif self.link_text is None:
                self.OUT += self.link
            self.inside_link = 0
            self.link = ''
            return
        if tag == 'p' and self.OFF:
            self.OFF = 0
        if self.OFF:
            return
        if len(self.OUT) > 2 and self.OUT[-1] == ' ':
            self.OUT += " "

    def handle_data(self, data):
        try:
            # print('handle data '+ data)
            if self.OFF:
                return
            data = re.sub(r'\n|\t', '', data)
            if self.inside_link:
                if (
                    data.startswith('#') or
                    data.startswith('@') or
                    self.link_text.startswith('#') or
                    self.link_text.startswith('@') or
                    self.mention or
                    self.last_char == '#' or
                    self.last_char == '@'
                ):
                    self.link_text += data
                else:
                    self.link_text = None
                return
            if data:
                self.OUT += data
                self.last_char = data[-1]
        except AttributeError:
            return

    def get_result(self):
        _a = self.OUT
        self.OUT = ''
        return _a

# instantiate the parser and fed it some HTML

# parser = MyHTMLParser()
# parser.feed('<html><head><title>Test</title></head>'
#             '<body><h1>Parse me!</h1></body></html>')
# parser.close()

# print(parser.get_result())
