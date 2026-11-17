"""적 기술의 영문 포함 전체 이름을 검수한 뒤에만 게시한다."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import monster_common as C
import qa_output as Q
Q.C=C

if __name__=='__main__':Q.main()
