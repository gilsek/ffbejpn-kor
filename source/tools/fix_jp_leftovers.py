"""Rule fixes for Japanese characters left inside Korean translations, and the list that needs re-translation."""
import json, re, glob, collections, sys
from pathlib import Path
TAG = re.compile(r'<[^>]*>')
HANGUL = re.compile(r'[가-힣]')
GLOSS = re.compile(r'\(([一-鿿々]+)\)|（([一-鿿々]+)）')            # 군도(軍都) -> 군도
def fix(s):
    s = GLOSS.sub('', s)
    # long-vowel mark: after a Hangul syllable/letter it stretches the sound -> '~'; otherwise a separator -> '-'
    s = re.sub(r'(?<=[가-힣ㄱ-ㅣ!?…])ー+', '~', s)
    s = re.sub(r'ー+', '-', s)
    return s
def left(s):
    t = TAG.sub('', s).replace('・', '')
    return bool(HANGUL.search(t) and re.search(r'[぀-ゟ゠-ヿ一-鿿]', t))
if __name__ == '__main__':
    tests = ['쿠ーー웅!', '퀘스트ー로이 머스탱ーLv4', '진짜로 군도(軍都)를 향해', '하아……困어라.', '빨강: 터프ポット']
    print([fix(t) for t in tests], [left(fix(t)) for t in tests])
