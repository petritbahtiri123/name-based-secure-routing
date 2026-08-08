package precedence

import (
	"fmt"

	"nbsr.example/federation-verifier/internal/strictjson"
)

var frozen = map[string]int{
	"ERR_RESOURCE_LIMIT": 1, "ERR_NON_CANONICAL": 2, "ERR_SIGNATURE_INVALID": 3,
	"ERR_IDENTITY": 4, "ERR_SCHEMA": 5, "ERR_AUTHORITY": 6, "ERR_ROLLBACK": 7,
	"ERR_REVOKED": 8, "ERR_TRANSPARENCY": 9, "ERR_FRESHNESS": 10, "ERR_LOCAL_POLICY": 11,
}

// Select applies the frozen protocol precedence without consulting vector oracles.
func Select(defects []string) (string, error) {
	got, best := "", 12
	for _, defect := range defects {
		rank, ok := frozen[defect]
		if !ok {
			return "", fmt.Errorf("unknown defect %q", defect)
		}
		if rank < best {
			got, best = defect, rank
		}
	}
	if got == "" {
		return "", fmt.Errorf("no defects")
	}
	return got, nil
}

type Rank struct {
	Class  string `json:"class"`
	Rank   int    `json:"rank"`
	Reason string `json:"reason"`
}
type Vector struct {
	Defects  []string `json:"defects"`
	Expected string   `json:"expected_reason"`
	ID       string   `json:"id"`
	RankPair []int    `json:"rank_pair"`
}
type Document struct {
	Authority     string   `json:"authority"`
	FormatVersion int      `json:"format_version"`
	Precedence    []Rank   `json:"precedence"`
	Vectors       []Vector `json:"vectors"`
}

func Verify(raw []byte) (int, []string, error) {
	var d Document
	if e := strictjson.Decode(raw, &d); e != nil {
		return 0, nil, e
	}
	seen := map[string]bool{}
	for _, r := range d.Precedence {
		if r.Rank < 1 || r.Rank > 11 || seen[r.Reason] || frozen[r.Reason] != r.Rank {
			return 0, nil, fmt.Errorf("invalid precedence")
		}
		seen[r.Reason] = true
	}
	if len(seen) != len(frozen) {
		return 0, nil, fmt.Errorf("incomplete precedence")
	}
	div := []string{}
	for _, v := range d.Vectors {
		got, err := Select(v.Defects)
		if err != nil {
			return 0, nil, err
		}
		if got != v.Expected {
			div = append(div, fmt.Sprintf("precedence %s got %s want %s", v.ID, got, v.Expected))
		}
	}
	return len(d.Vectors), div, nil
}
