from pathlib import Path
p=Path('artifacts/runs/20260920T190500-f3r1-rebuild/tmp/runner_f3r1.py'); t=p.read_text(encoding='utf-8'); a=t.index('ENGINE_SHA_EXPECT_FULL ='); b=t.index('FAMILY_DIR =',a); t=t[:a]+'ENGINE_SHA_EXPECT_FULL = "31022babbc2858ea27a9142141fba9c14f7361294ea84e4257025ce820aa6076"\n'+t[b:]; p.write_text(t,encoding='utf-8')

