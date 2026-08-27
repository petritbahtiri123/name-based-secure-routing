package resolution

import (
	"bytes"

	"nbsr.local/client/nbsr-go-client/internal/authority"
)

func cloneRouteContext(route RouteContext) RouteContext {
	route.Intent = cloneRouteIntent(route.Intent)
	return route
}

func cloneRouteIntent(intent authority.RouteIntent) authority.RouteIntent {
	intent.Canonical = append([]byte(nil), intent.Canonical...)
	intent.TargetEdges = append([]string(nil), intent.TargetEdges...)
	return intent
}

func sameRouteIntent(left, right authority.RouteIntent) bool {
	return bytes.Equal(left.Canonical, right.Canonical) && left.Digest == right.Digest &&
		left.ServiceIdentity == right.ServiceIdentity && left.SourceOperator == right.SourceOperator &&
		left.SourceEdge == right.SourceEdge && left.TargetOperator == right.TargetOperator &&
		sameStrings(left.TargetEdges, right.TargetEdges) && left.Transport == right.Transport &&
		left.Port == right.Port && left.RecordSequence == right.RecordSequence &&
		left.PolicyHash == right.PolicyHash && left.RouteID == right.RouteID &&
		left.LeaseID == right.LeaseID && left.ExpiresAt == right.ExpiresAt
}

func sameStrings(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}
