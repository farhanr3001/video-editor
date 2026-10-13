// Remove only processes/services whose executable resides in an app-owned root.
#include <windows.h>
#include <tlhelp32.h>
#include <string>
#include <vector>
#include <cwctype>
std::wstring lower(std::wstring s){for(auto &c:s)c=towlower(c);return s;}
bool owned(std::wstring value,const std::vector<std::wstring>& roots){
 value=lower(value);if(value.empty())return false;
 if(value[0]==L'"'){auto end=value.find(L'"',1);value=value.substr(1,end-1);}
 else {auto end=value.find(L".exe");if(end==std::wstring::npos)return false;value=value.substr(0,end+4);}
 for(auto root:roots){root=lower(root);while(!root.empty()&&(root.back()==L'\\'||root.back()==L'/'))root.pop_back();
 if(root.size()>3 && value.compare(0,root.size()+1,root+L"\\")==0)return true;}
 return false;
}
int wmain(int argc,wchar_t**argv){
 if(argc==2 && std::wstring(argv[1])==L"--selftest"){
 std::vector<std::wstring> r{L"C:\\Users\\Test\\AppData\\Local\\KineticCut"};
 if(!owned(L"\"C:\\Users\\Test\\AppData\\Local\\KineticCut\\components\\mDNSResponder.exe\" -service",r))return 10;
 if(owned(L"C:\\Program Files\\Bonjour\\mDNSResponder.exe",r))return 11;
 if(owned(L"C:\\Users\\Test\\AppData\\Local\\KineticCutOther\\mDNSResponder.exe",r))return 12;
 if(owned(L"C:\\Windows\\System32\\svchost.exe",r))return 13;
 return 0;
 }
 std::vector<std::wstring> roots;for(int i=1;i<argc;i++)roots.push_back(argv[i]);if(roots.empty())return 2;
 SC_HANDLE manager=OpenSCManagerW(nullptr,nullptr,SC_MANAGER_ENUMERATE_SERVICE|SC_MANAGER_CONNECT);if(!manager)return GetLastError();
 DWORD bytes=0,count=0,resume=0;EnumServicesStatusExW(manager,SC_ENUM_PROCESS_INFO,SERVICE_WIN32,SERVICE_STATE_ALL,nullptr,0,&bytes,&count,&resume,nullptr);
 std::vector<BYTE> buffer(bytes);resume=0;
 if(!EnumServicesStatusExW(manager,SC_ENUM_PROCESS_INFO,SERVICE_WIN32,SERVICE_STATE_ALL,buffer.data(),bytes,&bytes,&count,&resume,nullptr)){CloseServiceHandle(manager);return GetLastError();}
 auto entries=reinterpret_cast<ENUM_SERVICE_STATUS_PROCESSW*>(buffer.data());
 for(DWORD i=0;i<count;i++){
  SC_HANDLE service=OpenServiceW(manager,entries[i].lpServiceName,SERVICE_QUERY_CONFIG);if(!service)continue;
  DWORD size=0;QueryServiceConfigW(service,nullptr,0,&size);std::vector<BYTE> data(size);
  bool ours=size&&QueryServiceConfigW(service,reinterpret_cast<QUERY_SERVICE_CONFIGW*>(data.data()),size,&size)&&owned(reinterpret_cast<QUERY_SERVICE_CONFIGW*>(data.data())->lpBinaryPathName,roots);CloseServiceHandle(service);if(!ours)continue;
  service=OpenServiceW(manager,entries[i].lpServiceName,SERVICE_STOP|SERVICE_QUERY_STATUS|DELETE);
  if(!service){DWORD error=GetLastError();CloseServiceHandle(manager);return error==ERROR_ACCESS_DENIED?740:error;}
  SERVICE_STATUS status{};if(!ControlService(service,SERVICE_CONTROL_STOP,&status)&&GetLastError()!=ERROR_SERVICE_NOT_ACTIVE){DWORD error=GetLastError();CloseServiceHandle(service);CloseServiceHandle(manager);return error;}
  for(int n=0;n<100;n++){if(!QueryServiceStatus(service,&status)||status.dwCurrentState==SERVICE_STOPPED)break;Sleep(100);}
  if(status.dwCurrentState!=SERVICE_STOPPED){CloseServiceHandle(service);CloseServiceHandle(manager);return ERROR_TIMEOUT;}
  if(!DeleteService(service)&&GetLastError()!=ERROR_SERVICE_MARKED_FOR_DELETE){DWORD error=GetLastError();CloseServiceHandle(service);CloseServiceHandle(manager);return error;}
  CloseServiceHandle(service);
 }
 CloseServiceHandle(manager);
 HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);PROCESSENTRY32W entry{};entry.dwSize=sizeof(entry);
 if(Process32FirstW(snapshot,&entry))do{
  if(entry.th32ProcessID==GetCurrentProcessId())continue;
  HANDLE process=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|PROCESS_TERMINATE|SYNCHRONIZE,FALSE,entry.th32ProcessID);if(!process)continue;
  wchar_t path[32768];DWORD size=32768;if(QueryFullProcessImageNameW(process,0,path,&size)&&owned(path,roots)){
   // The uninstaller itself lives under the app root and must remain running.
   std::wstring name=lower(entry.szExeFile);if(name.find(L"unins")!=0){TerminateProcess(process,0);WaitForSingleObject(process,5000);}
  }CloseHandle(process);
 }while(Process32NextW(snapshot,&entry));CloseHandle(snapshot);return 0;
}
