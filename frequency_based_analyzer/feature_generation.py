__author__ = "Md. Ahsan Ayub"
__license__ = "GPL"
__credits__ = ["Ayub, Md. Ahsan", "Siraj, Ambareen"]
__maintainer__ = "Md. Ahsan Ayub"
__email__ = "mayub42@tntech.edu"
__status__ = "Prototype"


# Import libraries
import os
import glob
import hashlib
import magic
import pefile
import json
import requests

class SampleInfo(object):
	''' A class to hold a few basic pieces of information of the
	ransomware sample privided. '''

	def __init__(self, file_name, family_name):
		''' Initialize the contianer with the required information holders '''
		self._sample_info = {}
		self._sample_info['sample_file_name'] = file_name
		self._sample_info['family_name'] = family_name

	def set_sample_info(self):
		''' Extract important pieces of information about the sample '''

		# Collect the hashes of the file
		self._sample_info['md5'] = hashlib.md5()
		self._sample_info['sha1'] = hashlib.sha1()
		self._sample_info['sha256'] = hashlib.sha256()		

		with open(self._sample_info['sample_file_name'], 'rb') as f:
			buf = f.read()
			self._sample_info['md5'].update(buf)
			self._sample_info['sha1'].update(buf)
			self._sample_info['sha256'].update(buf)

		# Update the hashes
		self._sample_info['md5'] = self._sample_info['md5'].hexdigest()
		self._sample_info['sha1'] = self._sample_info['sha1'].hexdigest()
		self._sample_info['sha256'] = self._sample_info['sha256'].hexdigest()

		# Collect the file size in bytes
		self._sample_info['file_size'] = os.stat(self._sample_info['sample_file_name']).st_size
		# Collect the file type
		self._sample_info['file_type'] = magic.from_file(self._sample_info['sample_file_name'], mime=True)

	def get_sample_info(self):
		''' Get all the extracted data of the sample in dictionary format '''
		return self._sample_info


class peFileExtractor(object):
	''' This class is responsible to extract all the useful pieces
	of information of the ransomware samples using different libraries. '''

	def __init__(self, file_name):
		''' Initialize the contianer with the required information holders '''
		self._ransomware_sample_file_name = file_name
		self._pe_file_extracted_data = {}	# Dictnionary to store all the data

	def get_pe_file_extracted_data(self):
		''' Get all the extracted data in dictionary format '''
		return self._pe_file_extracted_data

	def set_pe_file_extracted_data(self):
		''' Extract all the PE file meta-data '''
		try:
			pe = pefile.PE(self._ransomware_sample_file_name)
		except OSError as e:
			print(e)
		except pefile.PEFormatError as e:
			print(e.value)

		''' Feature from the DOS Header '''
		# Could be MZ, stands for Mark Zbikowski, or ZM on an (non-PE) EXE
		self._pe_file_extracted_data['e_magic_value'] = hex(pe.DOS_HEADER.e_magic)[2:].decode("hex")
		# This is a relative address to the NT header (can't be null)
		self._pe_file_extracted_data['e_lfanew'] = hex(pe.DOS_HEADER.e_lfanew)

		''' Features from the File Header '''
		# Number identifying the type of the target (x14C - 32 bit ni+nary; x8664 - 64 bit binary)
		self._pe_file_extracted_data['target_machine'] = hex(pe.FILE_HEADER.Machine)
		# Indicates the size of the section table (Can be null)
		self._pe_file_extracted_data['number_of_section'] = int(hex(pe.FILE_HEADER.NumberOfSections), 16)
		# Time and date the file was created (used for bound import checks)
		self._pe_file_extracted_data['time_date_stamp'] = pe.FILE_HEADER.dump_dict()['TimeDateStamp']['Value'].split('[')[1][:-1]
		# Flags indicating the attributes of the file
		self._pe_file_extracted_data['characteristics'] = hex(pe.FILE_HEADER.Characteristics)

		''' Features from the Optional Header '''
		# Magic specifies the exact format of the PE file (x10b - 32bit; x20b - 64bit)
		self._pe_file_extracted_data['magic'] = hex(pe.OPTIONAL_HEADER.Magic)
		# Size of the code (text) section, or the sum of all code sections if there are multiple sections
		self._pe_file_extracted_data['size_of_code'] = int(hex(pe.OPTIONAL_HEADER.SizeOfCode), 16)
		# Size of the initialized data section, or the sum of all code sections if there are multiple data sections
		self._pe_file_extracted_data['size_of_initialized_data'] = int(hex(pe.OPTIONAL_HEADER.SizeOfInitializedData), 16)
		# Relative to the image base, when executable file is loaded into memory
		self._pe_file_extracted_data['entry_point_address'] = hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint)
		# Amount of contiguous memory that must be reserved to load the binary into memory
		self._pe_file_extracted_data['size_of_image'] = int(hex(pe.OPTIONAL_HEADER.SizeOfImage), 16)
		# Specifies the preferred virtual memory locaiton where the beginning of the binary should be placed
		self._pe_file_extracted_data['image_base'] = hex(pe.OPTIONAL_HEADER.ImageBase)
		# Specifies that sections must be aligned on boundaries which are multples of this value.
		self._pe_file_extracted_data['section_alignment'] = hex(pe.OPTIONAL_HEADER.SectionAlignment)
		# Specifies that the data written to the binary in chunks no smaller than this value
		self._pe_file_extracted_data['file_alignment'] = hex(pe.OPTIONAL_HEADER.FileAlignment)
		# Subsystem required to run this image file
		self._pe_file_extracted_data['subsystem'] = int(hex(pe.OPTIONAL_HEADER.Subsystem), 16)
		# Specifies some of the security characteristics for the PE file
		self._pe_file_extracted_data['dll_characteristics'] = hex(pe.OPTIONAL_HEADER.DllCharacteristics)
		# An array of data entries
		self._pe_file_extracted_data['number_of_data_directory'] = 0
		self._pe_file_extracted_data['data_directory'] = []
		for entry in pe.OPTIONAL_HEADER.DATA_DIRECTORY:
			self._pe_file_extracted_data['data_directory'].append(entry.name)
			self._pe_file_extracted_data['number_of_data_directory'] += 1

		'''Features for the sector headers '''
		''' Sections include:
		.text - code which should never be paged out of memory to disk
		.data - read/write data (globals)
		.rdata - read-only data (strings)
		.bss - block started by symbol or block storage segments
		.idata - import address table (it seems to merge with .text or .rdata)
		.edata - export information '''
		self._pe_file_extracted_data['number_of_pe_sections'] = 0
		self._pe_file_extracted_data['sections_info'] = {}
		for sections in pe.sections:
			temp = {}
			temp['section_name'] = str(sections.Name.decode().rstrip('\x00'))
			# The total size of the section when loading into memory.
			# Note: when it is more than SizeOfRawData, it indicates that the section is allocating
			# more memory space than it has data written to disk.
			temp['virtual_size'] = int(hex(sections.Misc_VirtualSize), 16)
			# The size of the section or the initialized data on disk
			temp['size_of_raw_data'] = int(hex(sections.SizeOfRawData), 16)
			# RVA of the section relative to OptinalHeader.ImageBase
			temp['virtual_address'] = hex(sections.VirtualAddress)
			# Relative offset from the beginning of the file which says where the actual section
			# data is stored
			temp['point_to_raw_data'] = hex(sections.PointerToRawData)
			temp['characteristics'] = hex(sections.Characteristics)

			self._pe_file_extracted_data['sections_info'][self._pe_file_extracted_data['number_of_pe_sections']] = temp
			self._pe_file_extracted_data['number_of_pe_sections'] += 1
		del temp

		''' Features of PE Version Info '''
		for version_info in pe.VS_VERSIONINFO:
			self._pe_file_extracted_data['version_info_length'] = hex(version_info.Length)
			self._pe_file_extracted_data['version_info_value_length'] = hex(version_info.ValueLength)
			self._pe_file_extracted_data['version_info_type'] = hex(version_info.Type)

		''' Features of Imported Symbols '''
		self._pe_file_extracted_data['imports_list'] = []
		self._pe_file_extracted_data['libraries_list'] = []
		self._pe_file_extracted_data['libraries_import_counts'] = {}
		for entry in pe.DIRECTORY_ENTRY_IMPORT:
			self._pe_file_extracted_data['libraries_list'].append(str(entry.dll.decode('utf-8')))
			self._pe_file_extracted_data['libraries_import_counts'][str(entry.dll.decode('utf-8'))] = 0
			for func in entry.imports:
				self._pe_file_extracted_data['imports_list'].append(str(func.name.decode('utf-8')))
				self._pe_file_extracted_data['libraries_import_counts'][str(entry.dll.decode('utf-8'))] += 1

		''' Features of Exported Symbols '''
		self._pe_file_extracted_data['exports_list'] = []
		try:
			for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
				self._pe_file_extracted_data['exports_list'].append(str(exp.name.decode('utf-8')))
		except:	# Does not have any export table entries
			pass


class VirusTotalReport(object):
	''' This class is reposible to scan the MD5 hash value of the sample
	with the Virus Total engine and store the analytics report. '''

	def __init__(self, api_key, resource):
		''' Initialize the contianer with the required information holders '''
		self._url = 'https://www.virustotal.com/vtapi/v2/file/report'
		self._params = {'apikey' : api_key, 'resource' : resource}
		self._vt_report = {}
		self._vt_report['number_of_engines_detected_safe'] = 0
		self._vt_report['number_of_engines_detected_malicious'] = 0
		self._vt_report['total_number_of_engines'] = 0

	def generate_report(self):
		''' Retrieve the VT scanned report with the parameters and store the info to the dictionary '''
		try:
			response_json = requests.get(self._url, params=self._params)
			response = response_json.json()
			for av_engine in response['scans']:
				if(response['scans'][av_engine]['detected'] == True):
					self._vt_report['number_of_engines_detected_malicious'] += 1
				if(response['scans'][av_engine]['detected'] == False):
					self._vt_report['number_of_engines_detected_safe'] += 1
				self._vt_report['total_number_of_engines'] += 1
		except:		# Something went wrong
			pass

	def get_report(self):
		''' Return the scanned results in dictionary format '''
		return self._vt_report


if __name__ == '__main__':
	''' Driver program '''

	# Store the current directory to dump the samples later
	current_directory = os.getcwd()
	
	# Change the directory to go where the samples are
	os.chdir("../samples/family_wise_samples/")

	# get all the ransomware familiy names
	all_ransomware_families = [i for i in glob.glob("*")]
	all_ransomware_families = sorted(all_ransomware_families)

	# Go to the family folder to scan each of its sample
	os.chdir("./" + all_ransomware_families[5] + "/")
	sample_names = [i for i in glob.glob("*")]
	sample_names = sorted(sample_names)

	# Extract the basic pieces of information regarding the PE file
	sample_info = SampleInfo(sample_names[0], all_ransomware_families[5])
	sample_info.set_sample_info()
	print(sample_info.get_sample_info())

	# Extract the information based on the PE module
	sample_pe_info = peFileExtractor(sample_names[0])
	sample_pe_info.set_pe_file_extracted_data()
	print(sample_pe_info.get_pe_file_extracted_data())

	vt_api_key = "<api_key>"
	vt_resource = sample_info.get_sample_info()['md5']
	vt_report = VirusTotalReport(vt_api_key, vt_resource)
	vt_report.generate_report()
	print(vt_report.get_report())