-- BOB-066 evidence-path repoint: qa-results/ (ignored) -> docs/qa/BOB-066/ (tracked).
BEGIN;

UPDATE items
   SET description = replace(description,
                             'qa-results/bob066/20260815T115831Z/',
                             'docs/qa/BOB-066/20260815T115831Z/')
 WHERE atm_id = 'BOB-066';

UPDATE item_history
   SET evidence_path = replace(evidence_path,
                               'qa-results/bob066/20260815T115831Z/',
                               'docs/qa/BOB-066/20260815T115831Z/')
 WHERE atm_id = 'BOB-066'
   AND evidence_path LIKE 'qa-results/bob066/%';

COMMIT;

.print --- verify BOB-066 evidence paths ---
SELECT atm_id, substr(description, -300, 300) FROM items WHERE atm_id = 'BOB-066';
.print --- verify item_history evidence_path ---
SELECT id, event_type, evidence_path FROM item_history WHERE atm_id = 'BOB-066' AND id = 65;
