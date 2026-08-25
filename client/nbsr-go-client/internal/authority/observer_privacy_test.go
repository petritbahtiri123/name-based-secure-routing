package authority

import (
	"reflect"
	"testing"
)

func TestObserverEventCarriesOnlyClosedDimensions(t *testing.T) {
	typeOfEvent := reflect.TypeOf(Event{})
	want := []reflect.Type{reflect.TypeOf(EventKind(0)), reflect.TypeOf(ErrorCode(0))}
	if typeOfEvent.NumField() != len(want) {
		t.Fatalf("authority observer Event has %d fields, want %d", typeOfEvent.NumField(), len(want))
	}
	for index := range want {
		if got := typeOfEvent.Field(index).Type; got != want[index] {
			t.Fatalf("authority observer Event field %d type = %v, want %v", index, got, want[index])
		}
	}
}
