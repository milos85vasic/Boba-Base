package service

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

// §11.4.135 regression guard for S5: GetSearchStatus returned a bare
// *SearchMetadata that was implicitly nil for a missing search_id. The
// comma-ok signature makes the missing-vs-present contract explicit and
// non-fragile. Present id => (meta,true); missing id => (nil,false).
func TestGetSearchStatus_CommaOk_Missing_S5(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	meta, ok := svc.GetSearchStatus("does-not-exist")
	assert.False(t, ok, "missing id must report ok=false")
	assert.Nil(t, meta, "missing id must return nil metadata")
}

func TestGetSearchStatus_CommaOk_Present_S5(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	started := svc.StartSearch("ubuntu", "all", true, true)
	meta, ok := svc.GetSearchStatus(started.SearchID)
	assert.True(t, ok, "present id must report ok=true")
	assert.NotNil(t, meta)
	assert.Equal(t, started.SearchID, meta.SearchID)
}
