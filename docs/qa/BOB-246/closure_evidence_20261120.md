=== test_commit_push_all_args (SUT=/home/milosvasic/Projects/boba/scripts/commit-push-all.sh) ===
PASS: T1 --scope after the message is honoured (committed: a.txt )
PASS: T2 --scope on both sides of the message is honoured (committed: a.txt c.txt )
PASS: T3 --scope=path after the message is honoured
PASS: T4 extra positional argument refused (exit 2, named, no commit)
PASS: T5 --scope-shaped token after -- refused (exit 2, no commit)
PASS: T6 commit message landed byte-for-byte (backticks, $(...), quotes, whitespace, newlines)
PASS: T6b message + recorded [skip-ci] tag landed byte-for-byte
PASS: T7 --message-file <path> landed byte-for-byte
PASS: T7b --message-file - (stdin) landed byte-for-byte
PASS: T8 message supplied twice refused (exit 2, no commit)
PASS: T9 control: flags-first scoped commit landed and was pushed to the (local bare) remote
PASS: T10 control: unscoped invocation keeps the documented git add -A default
PASS: T11 missing message refused (exit 2)

Total: PASS=13 FAIL=0
