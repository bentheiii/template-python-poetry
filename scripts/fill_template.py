import subprocess
import sys
import re
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from pprint import pprint
from typing import Mapping, Iterable, NamedTuple, Pattern, Callable, Optional, Any, Match

if sys.version_info < (3, 7, 0):
    raise RuntimeError(f'run in python 3.7 or higher')


def make_parser():
    ret = ArgumentParser()
    ret.add_argument('--delete-script', action='store_const', const=True, default=False, required=False, dest='del_script')
    ret.add_argument('--backup', action='store_const', const=True, default=False, required=False, dest='backup')
    return ret


# region decisions
DESCRIPTION_MAX_LEN: int = 20


class DecisionOption(NamedTuple):
    name: str
    value: Any

    def describe(self):
        chars_left = DESCRIPTION_MAX_LEN - len(self.name) - 3
        if chars_left <= 0:
            return self.name
        printable_value = self.value or repr(self.value)
        if len(printable_value) <= chars_left:
            return f'{self.name} ({printable_value})'
        chars_left -= 2
        if chars_left <= 2:
            return self.name
        side_len = chars_left // 2
        a, b = printable_value[:side_len], printable_value[-side_len:]
        return f'{self.name} ({a}..{b})'


class DecisionResolver:
    def load_resolved(self, resolved: Mapping[str, Any]):
        pass

    def options(self) -> Iterable[DecisionOption]:
        return iter(())

    custom_option: Optional[Callable[[str], Any]] = None

    def make(self, name):
        options = list(self.options())
        msg = [f'enter value for {name}:']
        for i, option in enumerate(options, 1):
            msg.append(f'{i}: {option.name} ({option.value})')
        if self.custom_option:
            msg.append('t: custom text')
        response = input('\n'.join(msg) + '\n')
        try:
            response_int = int(response)
        except ValueError:
            pass
        else:
            if response_int < len(options):
                return options[response_int]

        if self.custom_option and response == 't':
            custom = input('enter custom text:\n')
            try:
                return self.custom_option(custom)
            except Exception as e:
                print(e)
        print(f'could not parse {response}')
        return self.make(name)


class RegexDecisionValidator(DecisionResolver):
    def __init__(self, pattern: Optional[Pattern[str]] = None, pattern_description: str = "pattern"):
        super().__init__()
        self.pattern = pattern
        self.pattern_description = pattern_description
        if not self.pattern:
            self.custom_option = None

    def custom_option(self, x: str):
        if not self.pattern.fullmatch(x):
            raise ValueError(f'must match {self.pattern_description}')
        return x


class ConstResolver(RegexDecisionValidator):
    def __init__(self, options: Iterable[DecisionOption] = (), pattern: Pattern = None,
                 pattern_description: str = 'pattern'):
        super().__init__(pattern, pattern_description)
        self._options = set(options)

    def load_resolved(self, resolved: Mapping[str, Any]):
        self._options = {
            DecisionOption(do.name,
                           do.value.format_map(resolved) if hasattr(do.value, 'format_mapped') else do.value)
            for do in self._options
        }

    def add_option(self, option: DecisionOption):
        self._options.add(option)

    def options(self) -> Iterable[DecisionOption]:
        return self._options


author_pattern = '[a-zA-Z\s0-9_]+\s<[a-zA-Z._0-9]+@[a-zA-Z._0-9]+>'


class AuthorsResolver(ConstResolver):
    def __init__(self):
        super().__init__((), re.compile(author_pattern + "(,\s*" + author_pattern + ")*"),
                         "name <email>[, name <email>...]")

    def custom_option(self, x: str):
        return Authors(super().custom_option(x))


# endregion
# region decision-specific types
class License:
    def __init__(self, long: str, short: str):
        self.long = long
        self.short = short

    def format_map(self, m):
        return type(self)(self.long.format_map(m), self.short.format_map(m))

    def __str__(self):
        return self.long


class Authors:
    def __init__(self, x: str):
        self.parts = [a.strip() for a in x.split(',')]

    def split(self):
        return self.parts


class PyVersions:
    def __init__(self, semver, minors, preferred):
        self.semver = semver
        self._minors = minors
        self.preferred = preferred

    def minors(self):
        return ', '.join(self._minors)


# endregion


license_options = [
    DecisionOption('blank', License('', '')),
    DecisionOption('proprietary', License('Copyright (c) {year}, {authors}', 'Proprietary')),
    DecisionOption('MIT', License(
        'Copyright (c) {year}, {authors}\n\nPermission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice (including the next paragraph) shall be included in all copies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.',
        'MIT'))
]

py_version_options = [
    DecisionOption('^3.6', PyVersions('^3.6', ['3.6', '3.7', '3.8', '3.9'], '3.7')),
    DecisionOption('^3.7', PyVersions('^3.7', ['3.7', '3.8', '3.9'], '3.8')),
    DecisionOption('^3.8', PyVersions('^3.8', ['3.8', '3.9'], '3.8')),
    DecisionOption('^3.9', PyVersions('^3.9', ['3.9'], '3.9'))
]

platform_options = [
    DecisionOption('All Majors', 'ubuntu-latest, macos-latest, windows-latest'),
    DecisionOption('No Windows', 'ubuntu-latest, macos-latest'),
    DecisionOption('No Macos', 'ubuntu-latest, windows-latest'),
    DecisionOption('No Ubuntu', 'macos-latest, windows-latest'),
    DecisionOption('Windows', 'windows-latest'),
    DecisionOption('Macos', 'macos-latest'),
    DecisionOption('Ubuntu', 'ubuntu-latest'),
]

initial_version_options = [
    DecisionOption('0.0.1.dev', '0.0.1.dev'),
    DecisionOption('0.1.0.dev', '0.1.0.dev'),
    DecisionOption('1.0.0.dev', '1.0.0.dev'),
]
decisions = {
    'package': ConstResolver(pattern=re.compile('[a-zA-Z][a-zA-Z0-9_]*')),
    'authors': AuthorsResolver(),
    'year': ConstResolver(pattern=re.compile('[0-9]{4}')),
    'repo_link': ConstResolver(pattern=re.compile('.*')),
    'license': ConstResolver(license_options, pattern=re.compile('.*')),
    'py_versions': ConstResolver(py_version_options, pattern=re.compile('.*')),
    'os_platforms': ConstResolver(platform_options, pattern=re.compile('.*')),
    'inital_version': ConstResolver(initial_version_options, pattern=re.compile('.*')),
}


def run_and_get(*args, default=None):
    result = subprocess.run(*args, stdout=subprocess.PIPE, text=True)
    if result.returncode != 0:
        return default
    return result.stdout.strip()


def main():
    parser = make_parser()
    args = parser.parse_args()

    project_root = Path('.').absolute()
    if project_root.name == 'scripts':
        project_root = project_root.parent

    decisions['package'].add_option(DecisionOption('folder_name', project_root.name))
    decisions['year'].add_option(DecisionOption('current year', str(datetime.now().year)))

    username = run_and_get('git config user.name')
    if username:
        email = run_and_get('git config user.email')
        if email:
            decisions['authors'].add_option(DecisionOption('git user', Authors(f'{username} <{email}>')))

    remotes = run_and_get('git remote', default='').splitlines()
    for remote in remotes:
        url = run_and_get(f'git remote get-url {remote}')
        if url:
            if url.endswith('.git'):
                url = url[:-4]
            decisions['repo_link'].add_option(DecisionOption(remote, url))

    made_decisions = {}

    for name, resolver in decisions.items():
        made_decisions[name] = resolver.make(name)

    print('You are about to fill the project with the following values.'
          ' Enter a blank line to proceed or any other input to cancel.')
    pprint(made_decisions)
    response = input()
    if response:
        sys.exit(1)

    pattern = re.compile('<\$([^$]*)\$>')

    def repl(match: Match[str]):
        def inner(x: str):
            first, _, second = x.partition('!')
            if not second:
                return made_decisions[first]
            evaled_first = inner(first)
            evaled_second = getattr(evaled_first, second, None)
            if evaled_second is None:
                second_callback = eval(second)
                evaled_second = second_callback(evaled_second)
            if callable(evaled_second):
                evaled_second = evaled_second()
            return evaled_second

        return str(inner(match[1]))

    for file in project_root.rglob('*'):
        if file.suffix == '.bkp':
            continue
        if file.name == 'README.md':
            continue

        try:
            original = file.read_text()
        except UnicodeError:
            continue
        if args.backup and any(pattern.finditer(original)):
            backup = file.with_suffix('.bkp')
            backup.write_text(original)
        pattern.sub(repl, original)


    pkg_name = made_decisions['package']
    package_dir = (project_root / pkg_name)
    package_dir.mkdir()
    (package_dir / "_version.py").write_text("__version__ = 0.0.1dev")

    if args.del_script:
        



def quote(x):
    x = str(x)
    x = x.replace('"', r'\"')
    return '"' + x + '"'


def custom_text_hotswap(method: str):
    def ret(x: str):
        if not isinstance(x, str):
            raise TypeError(type(x))
        return input(f'enter result for custom text {x} with method {method}:\n')

    return ret


preferred = custom_text_hotswap('preferred')
split = custom_text_hotswap('short')
semver = custom_text_hotswap('semver')