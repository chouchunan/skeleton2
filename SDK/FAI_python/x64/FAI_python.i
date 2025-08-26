%module FAI_python
%include <windows.i>
%include <carrays.i>
%include <stdint.i>
%array_functions(uint8_t, uint8Array);
%include <cpointer.i>
%pointer_class(int64_t,int64p)
%pointer_class(size_t,sizep)
%pointer_class(int,intp)
%pointer_class(double,doublep)
%include <cstring.i>
%cstring_bounded_mutable(char *buf, 256)
%cstring_bounded_mutable(char *pBuf, 256)
%include <typemaps.i>
%apply int *OUTPUT {GenApiCNodeType* nodeType}
%apply int *OUTPUT {GenApiCVisibility* visibility}
%apply bool *OUTPUT {bool* result}

%{
#include <FAI_C/FAI_C.h>
#include <GenApi_C/FAGenApiC.h>
%}

#ifndef _WIN64
%define _WIN64
%enddef
#endif
#define _MSC_VER
#define CAMERA_EXPORTS
#define FA_GENAPI_C_EXPORTS

%include <fa_compiler.h>
%include <PFNC.h>

//FANodeMapHandle
%typemap(in) FANodeMapHandle %{
    $1 = (FANodeMapHandle)PyLong_AsVoidPtr($input);
%}
%typemap(in,numinputs=0) FANodeMapHandle* (void* tmp) %{
    $1 = (FANodeMapHandle*)&tmp;
%}
%typemap(argout) FANodeMapHandle* %{
    $result = SWIG_Python_AppendOutput($result,PyLong_FromVoidPtr(*$1));
%}

//FANodeHandle
%typemap(in) FANodeHandle %{
    $1 = (FANodeHandle)PyLong_AsVoidPtr($input);
%}
%typemap(in,numinputs=0) FANodeHandle* (void* tmp) %{
    $1 = (FANodeHandle*)&tmp;
%}
%typemap(argout) FANodeHandle* %{
    $result = SWIG_Python_AppendOutput($result,PyLong_FromVoidPtr(*$1));
%}

//FACallbackHandle
%typemap(in) FACallbackHandle %{
    $1 = (FACallbackHandle)PyLong_AsVoidPtr($input);
%}
%typemap(in,numinputs=0) FACallbackHandle* (void* tmp) %{
    $1 = (FACallbackHandle*)&tmp;
%}
%typemap(argout) FACallbackHandle* %{
    $result = SWIG_Python_AppendOutput($result,PyLong_FromVoidPtr(*$1));
%}

//FA_CAMERA_CALLBACK_HANDLE
%typemap(in) FA_CAMERA_CALLBACK_HANDLE %{
    $1 = (FA_CAMERA_CALLBACK_HANDLE)PyLong_AsVoidPtr($input);
%}
%typemap(in,numinputs=0) FA_CAMERA_CALLBACK_HANDLE* (void* tmp) %{
    $1 = (FA_CAMERA_CALLBACK_HANDLE*)&tmp;
%}
%typemap(argout) FA_CAMERA_CALLBACK_HANDLE* %{
    $result = SWIG_Python_AppendOutput($result,PyLong_FromVoidPtr(*$1));
%}

//ConfigurationEvent, ImageEvent callback
%typemap(in) FACameraCallbackFunction {
	$1 = (void (*)(FAI_CAMERA_HANDLE))PyLong_AsVoidPtr($input);
}

//CameraEvent callback
%typemap(in) FACallbackFunction {
	$1 = (void (*)(FANodeHandle))PyLong_AsVoidPtr($input);
}

%inline %{
static PyObject * GetBuffer(FaiGrabResult_t *pResult) {
	assert(pResult->pBuffer > 0);
	assert(pResult->BufferSize > 0);
	return PyByteArray_FromStringAndSize (pResult->pBuffer ,pResult->BufferSize); 
}
static PyObject * GetBufferFromImageInfo(FaiImageInfo_t *pResult) {
	assert(pResult->pBuffer > 0);
	assert(pResult->BufferSize > 0);
	return PyByteArray_FromStringAndSize (pResult->pBuffer ,pResult->BufferSize); 
}
FA_GENAPI_C_ERROR FABooleanGetValueByBool(FANodeHandle handle) {
	bool bool_value ;
	FABooleanGetValue(handle,&bool_value);
	if (bool_value)
		return true;
	else
		return false;
}
%}

%include <GenApi_C/FAGenApiCDefs.h>
%include <GenApi_C/FAGenApiCError.h>
%include <GenApi_C/FAGenApiC.h>
%include <FAI_C/FAI_C_Defs.h>
%include <FAI_C/FAI_C.h>

%pythoncode
%{
import ctypes

# a ctypes callback prototype
py_camera_callback_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
py_node_callback_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p)

def FAIDevice_RegisterConfigurationRemovalCallback(_self: "FAI_CAMERA_HANDLE", cbFn: "FACameraCallbackFunction") -> "FA_CAMERA_CALLBACK_HANDLE *":
	# wrap the python callback with a ctypes function pointer
	f1 = py_camera_callback_type(cbFn)
	# get the function pointer of the ctypes wrapper by casting it to void* and taking its value
	f1_ptr = ctypes.cast(f1, ctypes.c_void_p).value
	return _FAI_python.FAIDevice_RegisterConfigurationRemovalCallback(_self, f1_ptr)

def FAIDevice_RegisterImageGrabedCallback(_self: "FAI_CAMERA_HANDLE", cbFn: "FACameraCallbackFunction") -> "FA_CAMERA_CALLBACK_HANDLE *":
	# wrap the python callback with a ctypes function pointer
	f1 = py_camera_callback_type(cbFn)
	# get the function pointer of the ctypes wrapper by casting it to void* and taking its value
	f1_ptr = ctypes.cast(f1, ctypes.c_void_p).value
	return _FAI_python.FAIDevice_RegisterImageGrabedCallback(_self, f1_ptr)

def FANodeRegisterCallback(handle: "FANodeHandle", cbFn: "FACallbackFunction") -> "FACallbackHandle *":
	# wrap the python callback with a ctypes function pointer
	f1 = py_node_callback_type(cbFn)
	# get the function pointer of the ctypes wrapper by casting it to void* and taking its value
	f1_ptr = ctypes.cast(f1, ctypes.c_void_p).value
	return _FAI_python.FANodeRegisterCallback(handle, f1_ptr)
%}

