-- BOB-066 evidence path repoint: three raw .log files -> single curated evidence.md.
BEGIN;

UPDATE items
   SET description = replace(description,
                             'Evidence: docs/qa/BOB-066/20260815T115831Z/challenge_green.log, challenge_red.log, challenge_selfvalidate.log',
                             'Evidence: docs/qa/BOB-066/evidence.md')
 WHERE atm_id = 'BOB-066';

UPDATE item_history
   SET evidence_path = 'docs/qa/BOB-066/evidence.md'
 WHERE atm_id = 'BOB-066'
   AND id = 65;

COMMIT;

.print --- verify BOB-066 evidence path ---
SELECT atm_id, substr(description, -200, 200) FROM items WHERE atm_id = 'BOB-066';
SELECT id, evidence_path FROM item_history WHERE atm_id = 'BOB-066' AND id = 65;
