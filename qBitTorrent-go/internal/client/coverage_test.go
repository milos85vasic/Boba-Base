package client

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// loginHandler writes a successful qBittorrent login response (SID cookie + "Ok.").
func loginHandler(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{Name: "SID", Value: "sid"})
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("Ok."))
}

// newAuthedClient spins up a test server using the provided handler for non-login
// paths and returns an authenticated Client pointing at it.
func newAuthedClient(t *testing.T, handler http.HandlerFunc) (*Client, *httptest.Server) {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/auth/login" {
			loginHandler(w)
			return
		}
		handler(w, r)
	}))
	c, err := NewClient(server.URL, "admin", "admin")
	require.NoError(t, err)
	return c, server
}

// --- NewClient / Login error paths ---

func TestNewClient_InvalidURL(t *testing.T) {
	// url.Parse rejects a control character in the URL.
	_, err := NewClient("http://exa\x7fmple.com", "u", "p")
	assert.Error(t, err)
}

func TestNewClient_LoginNetworkError(t *testing.T) {
	// A syntactically valid URL pointing at an unroutable port: PostForm fails.
	_, err := NewClient("http://127.0.0.1:1", "u", "p")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "login request failed")
}

func TestLogin_RejectedBody(t *testing.T) {
	// HTTP 200 but body is not "Ok." -> login rejected.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("Fails."))
	}))
	defer server.Close()

	_, err := NewClient(server.URL, "admin", "admin")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "login rejected: Fails.")
}

func TestLogin_HTTPError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		_, _ = w.Write([]byte("forbidden"))
	}))
	defer server.Close()

	_, err := NewClient(server.URL, "admin", "admin")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "login failed: HTTP 403")
}

func TestLogin_NoSIDCookie(t *testing.T) {
	// Server returns Ok. without a SID cookie: login succeeds but sid stays empty.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("Ok."))
	}))
	defer server.Close()

	c, err := NewClient(server.URL, "admin", "admin")
	require.NoError(t, err)
	assert.False(t, c.IsAuthenticated())
	assert.Equal(t, "", c.GetSID())
}

// --- StartSearch ---

func TestStartSearch_SendsPluginsAndCategory(t *testing.T) {
	var gotPattern, gotCategory string
	var gotPlugins []string
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/search/start" {
			require.NoError(t, r.ParseForm())
			gotPattern = r.PostForm.Get("pattern")
			gotCategory = r.PostForm.Get("category")
			gotPlugins = r.PostForm["plugins"]
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]int{"id": 7})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	})
	defer server.Close()

	id, err := c.StartSearch("ubuntu", []string{"rutracker", "nnmclub"}, "movies")
	require.NoError(t, err)
	assert.Equal(t, 7, id)
	assert.Equal(t, "ubuntu", gotPattern)
	assert.Equal(t, "movies", gotCategory)
	assert.Equal(t, []string{"rutracker", "nnmclub"}, gotPlugins)
}

func TestStartSearch_HTTPError(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	})
	defer server.Close()

	id, err := c.StartSearch("x", nil, "all")
	require.Error(t, err)
	assert.Equal(t, 0, id)
	assert.Contains(t, err.Error(), "search start failed: HTTP 500")
}

func TestStartSearch_BadJSON(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("not-json"))
	})
	defer server.Close()

	id, err := c.StartSearch("x", nil, "all")
	require.Error(t, err)
	assert.Equal(t, 0, id)
	assert.Contains(t, err.Error(), "failed to decode search response")
}

// --- GetSearchResults ---

func TestGetSearchResults_QueryParams(t *testing.T) {
	var gotID, gotLimit, gotOffset string
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/search/results" {
			gotID = r.URL.Query().Get("id")
			gotLimit = r.URL.Query().Get("limit")
			gotOffset = r.URL.Query().Get("offset")
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(QBSearchResponse{
				Results: []QBSearchResult{{FileName: "a.iso", FileSize: 1234, NbSeeders: 9, NbLeechers: 3, FileURL: "magnet:?x"}},
				Total:   1,
				Status:  "Running",
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	})
	defer server.Close()

	results, total, err := c.GetSearchResults(55, 20, 40)
	require.NoError(t, err)
	assert.Equal(t, "55", gotID)
	assert.Equal(t, "20", gotLimit)
	assert.Equal(t, "40", gotOffset)
	assert.Equal(t, 1, total)
	require.Len(t, results, 1)
	assert.Equal(t, "a.iso", results[0].FileName)
	assert.Equal(t, int64(1234), results[0].FileSize)
	assert.Equal(t, 9, results[0].NbSeeders)
	assert.Equal(t, 3, results[0].NbLeechers)
	assert.Equal(t, "magnet:?x", results[0].FileURL)
}

func TestGetSearchResults_OmitsZeroLimitOffset(t *testing.T) {
	var hadLimit, hadOffset bool
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/search/results" {
			_, hadLimit = r.URL.Query()["limit"]
			_, hadOffset = r.URL.Query()["offset"]
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(QBSearchResponse{Total: 0})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	})
	defer server.Close()

	_, _, err := c.GetSearchResults(1, 0, 0)
	require.NoError(t, err)
	assert.False(t, hadLimit, "limit should be omitted when 0")
	assert.False(t, hadOffset, "offset should be omitted when 0")
}

func TestGetSearchResults_HTTPError(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	})
	defer server.Close()

	results, total, err := c.GetSearchResults(1, 0, 0)
	require.Error(t, err)
	assert.Nil(t, results)
	assert.Equal(t, 0, total)
	assert.Contains(t, err.Error(), "failed to get results: HTTP 503")
}

func TestGetSearchResults_BadJSON(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("{bad"))
	})
	defer server.Close()

	_, _, err := c.GetSearchResults(1, 0, 0)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "failed to decode results")
}

// --- StopSearch ---

func TestStopSearch_SendsID(t *testing.T) {
	var gotID string
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/search/stop" {
			require.NoError(t, r.ParseForm())
			gotID = r.PostForm.Get("id")
			w.WriteHeader(http.StatusOK)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	})
	defer server.Close()

	require.NoError(t, c.StopSearch(99))
	assert.Equal(t, "99", gotID)
}

func TestStopSearch_HTTPError(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusConflict)
	})
	defer server.Close()

	err := c.StopSearch(99)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "failed to stop search: HTTP 409")
}

// --- SearchStatus ---

func TestSearchStatus_Success(t *testing.T) {
	var gotID string
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/search/status" {
			gotID = r.URL.Query().Get("id")
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]string{"status": "Stopped"})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	})
	defer server.Close()

	status, err := c.SearchStatus(13)
	require.NoError(t, err)
	assert.Equal(t, "Stopped", status)
	assert.Equal(t, "13", gotID)
}

func TestSearchStatus_BadJSON(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("oops"))
	})
	defer server.Close()

	status, err := c.SearchStatus(1)
	require.Error(t, err)
	assert.Equal(t, "", status)
}

// --- ListPlugins ---

func TestListPlugins_Success(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/search/plugins" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode([]map[string]interface{}{
				{"name": "rutracker", "enabled": true},
				{"name": "nnmclub", "enabled": false},
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	})
	defer server.Close()

	plugins, err := c.ListPlugins()
	require.NoError(t, err)
	require.Len(t, plugins, 2)
	assert.Equal(t, "rutracker", plugins[0]["name"])
	assert.Equal(t, true, plugins[0]["enabled"])
	assert.Equal(t, "nnmclub", plugins[1]["name"])
}

func TestListPlugins_HTTPError(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	})
	defer server.Close()

	plugins, err := c.ListPlugins()
	require.Error(t, err)
	assert.Nil(t, plugins)
	assert.Contains(t, err.Error(), "failed to list plugins: HTTP 500")
}

func TestListPlugins_BadJSON(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("not-an-array"))
	})
	defer server.Close()

	_, err := c.ListPlugins()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "failed to decode plugins")
}

// --- GetTorrents ---

func TestGetTorrents_Success(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/torrents/info" {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode([]map[string]interface{}{
				{"name": "Ubuntu", "progress": 1.0},
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	})
	defer server.Close()

	torrents, err := c.GetTorrents()
	require.NoError(t, err)
	require.Len(t, torrents, 1)
	assert.Equal(t, "Ubuntu", torrents[0]["name"])
	assert.Equal(t, 1.0, torrents[0]["progress"])
}

func TestGetTorrents_HTTPError(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	})
	defer server.Close()

	torrents, err := c.GetTorrents()
	require.Error(t, err)
	assert.Nil(t, torrents)
	assert.Contains(t, err.Error(), "failed to get torrents: HTTP 403")
}

func TestGetTorrents_BadJSON(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("{}"))
	})
	defer server.Close()

	_, err := c.GetTorrents()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "failed to decode torrents")
}

// --- AddTorrent ---

func TestAddTorrent_SendsAllFields(t *testing.T) {
	var gotURLs, gotSavepath, gotCategory string
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/torrents/add" {
			require.NoError(t, r.ParseForm())
			gotURLs = r.PostForm.Get("urls")
			gotSavepath = r.PostForm.Get("savepath")
			gotCategory = r.PostForm.Get("category")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte("Ok."))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	})
	defer server.Close()

	require.NoError(t, c.AddTorrent("magnet:?xt=urn:btih:abc", "/downloads", "movies"))
	assert.Equal(t, "magnet:?xt=urn:btih:abc", gotURLs)
	assert.Equal(t, "/downloads", gotSavepath)
	assert.Equal(t, "movies", gotCategory)
}

func TestAddTorrent_FailsBody(t *testing.T) {
	// HTTP 200 but body "Fails." -> error.
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/torrents/add" {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte("Fails."))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	})
	defer server.Close()

	err := c.AddTorrent("http://x/y.torrent", "", "")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "add torrent failed")
}

func TestAddTorrent_HTTPError(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	})
	defer server.Close()

	err := c.AddTorrent("http://x/y.torrent", "", "")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "add torrent failed: HTTP 500")
}

// --- AddTorrentFile ---

func TestAddTorrentFile_Success(t *testing.T) {
	var gotContentType, gotFilename string
	var gotFileContents []byte
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/torrents/add" {
			gotContentType = r.Header.Get("Content-Type")
			require.NoError(t, r.ParseMultipartForm(1<<20))
			f, hdr, err := r.FormFile("torrents")
			require.NoError(t, err)
			defer f.Close()
			gotFilename = hdr.Filename
			gotFileContents, _ = io.ReadAll(f)
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte("Ok."))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	})
	defer server.Close()

	payload := []byte("d8:announce4:teste")
	require.NoError(t, c.AddTorrentFile("my.torrent", payload))
	assert.True(t, strings.HasPrefix(gotContentType, "multipart/form-data"))
	assert.Equal(t, "my.torrent", gotFilename)
	assert.Equal(t, payload, gotFileContents)
}

func TestAddTorrentFile_FailsBody(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/torrents/add" {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte("Fails."))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	})
	defer server.Close()

	err := c.AddTorrentFile("my.torrent", []byte("data"))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "upload torrent failed")
}

func TestAddTorrentFile_HTTPError(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
	})
	defer server.Close()

	err := c.AddTorrentFile("my.torrent", []byte("data"))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "upload torrent failed: HTTP 400")
}

// --- GetAppVersion ---

func TestGetAppVersion_Success(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/app/version" {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte("v4.6.0"))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	})
	defer server.Close()

	version, err := c.GetAppVersion()
	require.NoError(t, err)
	assert.Equal(t, "v4.6.0", version)
}

func TestGetAppVersion_HTTPErrorReturnsUnknown(t *testing.T) {
	c, server := newAuthedClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	})
	defer server.Close()

	version, err := c.GetAppVersion()
	require.NoError(t, err)
	assert.Equal(t, "unknown", version)
}
