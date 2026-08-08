// Package strictjson provides duplicate-aware, unknown-field rejecting JSON.
package strictjson

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"math"
)

const maxDepth = 96

func Decode(raw []byte, dst any) error {
	if err := Validate(raw); err != nil {
		return err
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	d.UseNumber()
	if err := d.Decode(dst); err != nil {
		return err
	}
	if err := d.Decode(new(any)); err != io.EOF {
		return fmt.Errorf("trailing JSON data")
	}
	return nil
}

// Validate rejects duplicate keys and trailing data without imposing a schema.
func Validate(raw []byte) error {
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	if err := value(d, 0); err != nil {
		return err
	}
	if tok, err := d.Token(); err != io.EOF {
		return fmt.Errorf("trailing JSON token %v: %w", tok, err)
	}
	return nil
}

func value(d *json.Decoder, depth int) error {
	if depth > maxDepth {
		return fmt.Errorf("JSON depth limit exceeded")
	}
	t, err := d.Token()
	if err != nil {
		return err
	}
	delim, ok := t.(json.Delim)
	if !ok {
		if number, isNumber := t.(json.Number); isNumber {
			f, err := number.Float64()
			if err != nil || math.IsInf(f, 0) || (math.Trunc(f) == f && math.Abs(f) > 9007199254740991) {
				return fmt.Errorf("JSON integer outside safe range")
			}
		}
		return nil
	}
	switch delim {
	case '{':
		seen := map[string]struct{}{}
		for d.More() {
			kt, err := d.Token()
			if err != nil {
				return err
			}
			k, ok := kt.(string)
			if !ok {
				return fmt.Errorf("non-string object key")
			}
			if _, exists := seen[k]; exists {
				return fmt.Errorf("duplicate JSON key %q", k)
			}
			seen[k] = struct{}{}
			if err := value(d, depth+1); err != nil {
				return err
			}
		}
		end, err := d.Token()
		if err != nil || end != json.Delim('}') {
			return fmt.Errorf("unterminated object")
		}
	case '[':
		for d.More() {
			if err := value(d, depth+1); err != nil {
				return err
			}
		}
		end, err := d.Token()
		if err != nil || end != json.Delim(']') {
			return fmt.Errorf("unterminated array")
		}
	default:
		return fmt.Errorf("unexpected delimiter")
	}
	return nil
}
