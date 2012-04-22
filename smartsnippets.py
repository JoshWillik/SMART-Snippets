import sublime
import sublime_plugin
import os.path
import re

class SmartSnippetListener(sublime_plugin.EventListener):

    def on_activated(self,view):
        self.view = view

    def has_tabstop(self, view):
        return bool(RunSmartSnippetCommand.global_ts_order.get(view.id()))

    def replace(self, item):
        if item < 0: return
        view = self.view
        r = view.get_regions('quick_completions')
        word = r[self.i]
        text = RunSmartSnippetCommand.global_quickcompletions.get(view.id())[self.i][item]
        edit = view.begin_edit()
        view.replace(edit, word, text)
        r[self.i] = sublime.Region(word.a,word.a+len(text))
        view.add_regions('quick_completions', r, 'comment')
        view.sel().clear()
        view.sel().add(word.a+len(text))
        view.end_edit(edit)

    def match_scope(self, view, snip_file):
        scope = view.scope_name(view.sel()[0].a)
        has_no_scope = True
        f = open(snip_file, 'r')
        for line in f:
            if line.startswith('###scope'):
                has_no_scope = False
                param, snip_scope = line.split(":",1)
                if snip_scope.strip() in scope:
                    f.close()
                    return True
        f.close()
        return has_no_scope

    # Checks the SMART Snippet package for a snippet with the name of the preceding text
    def prev_word_is_trigger(self, view):
        trigger = view.substr(view.word(view.sel()[0].a)).strip()
        snip_file = sublime.packages_path() + "/SMART_Snippets/" + trigger + ".smart_snippet"
        return os.path.isfile(snip_file) and self.match_scope(view, snip_file)

    # For checking if the cursor selection overlaps with a QP region
    def on_selection_modified(self, view):
        sel = view.sel()[0]
        regions = view.get_regions('quick_completions')
        for i,r in enumerate(regions[:]):
            if r.empty() and not ' ' in view.substr(sel.a-1):
                regions.remove(r)
                # qp = RunSmartSnippetCommand.global_quickcompletions.get(view.id()).pop(i)

        for i,r in enumerate(regions):
            if sel == r:
                self.i = i
                qp = RunSmartSnippetCommand.global_quickcompletions.get(view.id())[i]
                view.window().show_quick_panel(qp, self.replace)
        
        view.add_regions('quick_completions', regions, 'comment')

    # adds a context for 'tab' in the keybindings
    def on_query_context(self, view, key, operator, operand, match_all):
        if key == "smart_snippet_found":
            return self.prev_word_is_trigger(view) == operand
        if key == "has_smart_tabstop":
            return self.has_tabstop(view) == operand

    # if cursor overlaps with AC region, get the available completions
    def on_query_completions(self, view, prefix, locations):
        sel = view.sel()[0]
        regions = view.get_regions('smart_completions')
        for i,r in enumerate(regions):
            if r.contains(sel):
                if r == sel:
                    edit = view.begin_edit()
                    view.erase(edit, r)
                    view.end_edit(edit)
                ac = RunSmartSnippetCommand.global_autocompletions.get(view.id())[i]
                return [(x,x) for x in ac]

# If has_tabstop, this class allows for tabbing between tabstops.
# To avoid duplicate code between the eventlistener and textcommand, it gets its own class
class NextSmartTabstopCommand(sublime_plugin.TextCommand):
    def run(self,edit):
        view = self.view
        tabstops = self.view.get_regions('smart_tabstops')
        ts_order = RunSmartSnippetCommand.global_ts_order.get(view.id())
        next = tabstops.pop(ts_order.index(min(ts_order)))
        RunSmartSnippetCommand.global_ts_order[view.id()].remove(min(ts_order))
        view.add_regions('smart_tabstops', tabstops, 'comment')
        view.sel().clear()
        view.sel().add(next)

class RunSmartSnippetCommand(sublime_plugin.TextCommand):
    # global dictionaries to give access the autocompletions and quickcompletions
    # key = view id
    global_autocompletions = {}
    global_quickcompletions = {}
    global_ts_order = {}
    temp_tabstops = []
    ac_regions    = []
    qc_regions    = []

    # This is a working list of substitutions for embedded code.
    # It will serve as shorthand for people who want quick access to common python functions and commands
    reps = [
            # ('([\w]+)\s*='             , 'global \\1\n\\1 ='),
            ('insert\('                ,'self.insert(edit,'),
            ('\%line\%'                ,'substr(line(sel))'),
            ('%prev_word%'             ,'substr(word(sel))'),
            ('(?<!_)word\('            , 'view.word('),
            ('substr'                  , 'view.substr'),
            ('sel(?!f)'                , 'view.sel()[0]'),
            ('line\('                  , 'view.line('),
            ('view'                    , 'self.view')
            ]

    def replace_all(self, text, list):
        for i, j in list:
            text = re.sub(i, j, text)
        return text

    def insert(self, edit, string):
        if self.code_in_snip[0]:
            self.code_in_snip[1] = string
            return
        self.view.insert(edit, self.pos, string)
        self.pos += len(string)

    def matches_scope(self, line, scope):
        param, snip_scope = line.split(":",1)
        return snip_scope.strip() in scope

    # replace the shorthand code with the reps,
    # then exec the code segment
    # def run_code(self, edit, string):
    #     new_string = self.replace_all(string, self.reps)
    #     exec new_string[3:-3]

    # used to parse snippets to extract the string that will be printed out
    # ex. ${0:snippet}
    #           ^
    # The method finds the word snippet and returns it to be inserted into the view
    def get_vis(self, word):
        if word.startswith('$'):
            overlap = word[4:].find('{')
            if overlap > 0 and not '\\' in word[overlap:overlap+1]: # means there is an overlapping region.
                start = overlap + 5
                end = word[4:].find(':')+4
                other_end = word.find('}')
                new_word = word[start:end]
                r = sublime.Region(self.pos,self.pos+len(new_word)) #added -1
                rlist = word[end+1:other_end]
                if word.startswith('AC'):
                    self.ac_regions.append(r)
                    self.global_autocompletions[self.view.id()].append(rlist.split(','))
                else:
                    self.qc_regions.append(r)
                    self.global_quickcompletions[self.view.id()].append(rlist.split(','))
            else:
                start = word.find(':')+1
                end = word.find('}')
            new_word = word[start:end]
            ts_index = re.search('\d{1,2}',word).group()
            if ts_index == '0':
                ts_index = 100
            ts_region = sublime.Region(self.pos,self.pos+len(new_word))
            temp = (ts_region, int(ts_index))
            self.temp_tabstops.append(temp)
        else:
            start = word.find('{')+1
            end = word.find(':')
            other_end = word.find('}')
            new_word = word[start:end]
            r = sublime.Region(self.pos,self.pos+len(new_word)) # added -1
            rlist = word[end+1:other_end]
            if word.startswith('AC'):
                self.ac_regions.append(r)
                self.global_autocompletions[self.view.id()].append(rlist.split(','))
            else:
                self.qc_regions.append(r)
                self.global_quickcompletions[self.view.id()].append(rlist.split(','))
        return new_word

    def parse_snippet(self,edit,contents,scope):
        view = self.view
        is_valid_scope = False
        new_contents = ''
        self.code_in_snip = [False,'']
        self.pos = self.get_trigger_reg().a
        view.erase(edit, self.get_trigger_reg())

        # Divides the string so that only code with a matching scope will be inserted
        for line in contents.splitlines(True):
            if line.startswith('###'):
                if line.startswith('###scope:'):
                    is_valid_scope = self.matches_scope(line,scope)
            elif is_valid_scope:
                new_contents += line

        for word in re.split(r'((?:\$|AC|QP)\{[^\{]+?(?:(?=\{)[\w\s:,\{]+\}|[^\}]+)\s*\}|```[^`]+```)',new_contents):
            if word.startswith(('$','AC','QP')):
                for code in re.findall('```[^`]+```', word, flags=re.DOTALL):
                    self.code_in_snip[0] = True
                    exec self.replace_all(code, self.reps)[3:-3]
                    word = word.replace(code,str(self.code_in_snip[1]))
                visible_word = self.get_vis(word)
            elif word.startswith('```'):
                exec self.replace_all(word, self.reps)[3:-3]
                visible_word = ''
            else:
                visible_word = word

            view.insert(edit,self.pos,visible_word)
            self.pos += len(visible_word)
            view.sel().clear()
            view.sel().add(sublime.Region(self.pos,self.pos))

        stop_regions = [x[0] for x in self.temp_tabstops]
        self.global_ts_order[view.id()] = [x[1] for x in self.temp_tabstops]

        view.add_regions('smart_tabstops', stop_regions, 'comment')
        view.add_regions('smart_completions', self.ac_regions, 'comment')
        view.add_regions('quick_completions', self.qc_regions, 'comment')
        del self.temp_tabstops[:]
        del self.ac_regions[:]
        del self.qc_regions[:]
    
    def snippet_contents(self):
        trigger = self.get_trigger()
        package_dir = sublime.packages_path() + "/SMART_Snippets/"
        snip_file = package_dir + trigger + ".smart_snippet"
        with open(snip_file, 'r') as f:
            return f.read()

    # gets the previous word
    def get_trigger(self):
        return self.view.substr(self.get_trigger_reg())

    # returns the region of the previous word
    def get_trigger_reg(self):
        sel = self.view.sel()[0]
        return self.view.word(sel.a)

    def run(self, edit):
        view      = self.view
        sel       = view.sel()[0]
        scope     = view.scope_name(sel.a)
        snippet   = self.snippet_contents()
        self.global_autocompletions[view.id()] = []
        self.global_quickcompletions[view.id()] = []
        self.parse_snippet(edit,snippet, scope)

        # if there is a tabstop, set the cursor to the first tabstop.
        if view.get_regions('smart_tabstops'):
            self.view.run_command("next_smart_tabstop")