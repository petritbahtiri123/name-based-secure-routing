//go:build connector_development

package connector
import("os";"testing")
func TestCoordinatorAvailable(t *testing.T){if _,err:=os.Stat("coordinator.go");err!=nil{t.Fatal("in-memory coordinator not implemented")}}
