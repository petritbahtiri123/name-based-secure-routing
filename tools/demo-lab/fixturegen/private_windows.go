package main

import (
	"syscall"
	"unsafe"
)

func privateDirectory(path string) error {
	token, err := syscall.OpenCurrentProcessToken()
	if err != nil {
		return err
	}
	defer token.Close()
	user, err := token.GetTokenUser()
	if err != nil {
		return err
	}
	sid, err := user.User.Sid.String()
	if err != nil {
		return err
	}
	sddl, err := syscall.UTF16PtrFromString("D:P(A;OICI;FA;;;" + sid + ")(A;OICI;FA;;;SY)")
	if err != nil {
		return err
	}
	var descriptor uintptr
	convert := syscall.NewLazyDLL("advapi32.dll").NewProc("ConvertStringSecurityDescriptorToSecurityDescriptorW")
	ok, _, callErr := convert.Call(uintptr(unsafe.Pointer(sddl)), 1, uintptr(unsafe.Pointer(&descriptor)), 0)
	if ok == 0 {
		return callErr
	}
	defer syscall.LocalFree(syscall.Handle(descriptor))
	attrs := syscall.SecurityAttributes{Length: uint32(unsafe.Sizeof(syscall.SecurityAttributes{})), SecurityDescriptor: descriptor}
	name, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return err
	}
	return syscall.CreateDirectory(name, &attrs)
}
