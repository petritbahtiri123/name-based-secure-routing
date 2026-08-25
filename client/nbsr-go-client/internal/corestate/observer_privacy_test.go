package corestate

import (
	"reflect"
	"testing"
)

func TestObserverEventCarriesOnlyClosedKind(t *testing.T) {
	typeOfEvent := reflect.TypeOf(Event{})
	if typeOfEvent.NumField() != 1 || typeOfEvent.Field(0).Type != reflect.TypeOf(EventKind(0)) {
		t.Fatalf("core observer Event fields = %v, want EventKind only", eventFieldTypes(typeOfEvent))
	}
}

func eventFieldTypes(event reflect.Type) []reflect.Type {
	fields := make([]reflect.Type, event.NumField())
	for index := range event.NumField() {
		fields[index] = event.Field(index).Type
	}
	return fields
}
