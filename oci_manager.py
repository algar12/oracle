import os
import oci
from dotenv import load_dotenv

class OciManager:
    def __init__(self, env_path='.env'):
        load_dotenv(env_path)
        
        self.region = os.getenv('OCI_REGION')
        self.user = os.getenv('OCI_USER_ID')
        self.tenancy = os.getenv('OCI_TENANCY_ID')
        self.fingerprint = os.getenv('OCI_KEY_FINGERPRINT')
        self.key_file = os.getenv('OCI_PRIVATE_KEY_FILENAME')
        
        self.subnet_id = os.getenv('OCI_SUBNET_ID')
        self.image_id = os.getenv('OCI_IMAGE_ID')
        self.shape = os.getenv('OCI_SHAPE', 'VM.Standard.A1.Flex')
        
        # Flex shape details
        self.ocpus = float(os.getenv('OCI_OCPUS', '4'))
        self.memory_in_gbs = float(os.getenv('OCI_MEMORY_IN_GBS', '24'))
        
        self.ssh_key = os.getenv('OCI_SSH_PUBLIC_KEY')
        self.max_instances = int(os.getenv('OCI_MAX_INSTANCES', '1'))
        self.boot_volume_size = os.getenv('OCI_BOOT_VOLUME_SIZE_IN_GBS')
        self.boot_volume_id = os.getenv('OCI_BOOT_VOLUME_ID')
        
        self.ad_config = os.getenv('OCI_AVAILABILITY_DOMAIN', '')
        
        self.config = {
            "user": self.user,
            "key_file": self.key_file,
            "fingerprint": self.fingerprint,
            "tenancy": self.tenancy,
            "region": self.region
        }
        
        try:
            oci.config.validate_config(self.config)
            self.compute_client = oci.core.ComputeClient(self.config)
            self.identity_client = oci.identity.IdentityClient(self.config)
        except Exception as e:
            print(f"Error initializing OCI client: {e}")
            self.compute_client = None

    def get_availability_domains(self):
        try:
            response = self.identity_client.list_availability_domains(self.tenancy)
            return [ad.name for ad in response.data]
        except Exception as e:
            print(f"Error fetching ADs: {e}")
            return []

    def check_existing_instances(self):
        """Check if we already have the maximum number of instances running."""
        try:
            response = self.compute_client.list_instances(
                compartment_id=self.tenancy,
            )
            
            count = 0
            for instance in response.data:
                if instance.lifecycle_state not in ['TERMINATED', 'TERMINATING']:
                    if instance.shape == self.shape:
                        count += 1
            return count >= self.max_instances, count
        except Exception as e:
            print(f"Error checking instances: {e}")
            return False, -1

    def launch_instance(self, availability_domain):
        """Attempt to launch an instance in the given Availability Domain."""
        shape_config = oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=self.ocpus,
            memory_in_gbs=self.memory_in_gbs
        )

        source_details = oci.core.models.InstanceSourceViaImageDetails(
            source_type="image",
            image_id=self.image_id
        )
        
        if self.boot_volume_size:
            source_details.boot_volume_size_in_gbs = int(self.boot_volume_size)
            
        if self.boot_volume_id:
            source_details = oci.core.models.InstanceSourceViaBootVolumeDetails(
                source_type="bootVolume",
                boot_volume_id=self.boot_volume_id
            )

        create_vnic_details = oci.core.models.CreateVnicDetails(
            subnet_id=self.subnet_id,
            assign_public_ip=True
        )

        launch_details = oci.core.models.LaunchInstanceDetails(
            compartment_id=self.tenancy,
            availability_domain=availability_domain,
            shape=self.shape,
            shape_config=shape_config,
            source_details=source_details,
            create_vnic_details=create_vnic_details,
            metadata={
                "ssh_authorized_keys": self.ssh_key.strip('"\'') if self.ssh_key else ""
            }
        )

        try:
            response = self.compute_client.launch_instance(launch_details)
            return True, response.data
        except oci.exceptions.ServiceError as e:
            return False, e.message
        except Exception as e:
            return False, str(e)
