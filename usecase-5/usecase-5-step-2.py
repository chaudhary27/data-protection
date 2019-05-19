"""
##########################################################################################
# Create a subordinate private certificate authority(CA) using AWS Certfificate Manager  #
##########################################################################################
"""
import os
import subprocess
import sys
import random
import json
import time
import boto3

def main():
    """
    #########################################################################################
    #  Create a CRL S3 bucket and a subordinate private certificate authority(CA) using ACM #
    #########################################################################################
    """
    try:
        acm_pca_client = boto3.client('acm-pca')
        s3_client = boto3.client('s3'   )
        ssm_client = boto3.client('ssm')
        
        ####################################################################
        #   Creating the subject for the private certificate authority     #
        ####################################################################
        subordinate_ca_serial_number = random.randint(1, 100000)
        common_name = 'dp-workshop.subordinate'
        
        subject = {
            'Country': 'US',
            'Organization': 'customer',
            'OrganizationalUnit': 'customerdept',
            'State': 'Nevada',
            'CommonName': common_name,
            'SerialNumber': unicode(str(subordinate_ca_serial_number)),
            'Locality': 'Las Vegas'
        }
        
        #################################################################################
        #   Create an S3 bucket for storing certificate revocation lists(crl)           #
        #                                                                               #
        #   Also tag the bucket so that it can be associated with this builders session #
        #   for cleanup                                                                 #
        #################################################################################
        crl_bucket_name = 'builder-acm-pca-usecase-6-bucket-pca-crl' + str(random.randint(1, 100000))
        # Doing the below because locationconstraint does not support all regions today
        region = boto3.Session().region_name
        if 'us-east-1' in region:
            s3_client.create_bucket(Bucket=crl_bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=crl_bucket_name,
                CreateBucketConfiguration={
                    'LocationConstraint': region
                }
            )
        
        waiter = s3_client.get_waiter('bucket_exists')
        waiter.wait(Bucket=crl_bucket_name)
        response = s3_client.put_bucket_tagging(
            Bucket=crl_bucket_name,
            Tagging={
                'TagSet': [
                    {
                        'Key': 'workshop',
                        'Value': 'data-protection'
                    },
                ]
            }
        )
        
        #################################################################################
        #   ACM service should be able to write/update crl to this S3 bucket            #
        #   therefore we need to put a bucket policy which gives permission to ACM      #
        #                                                                               #
        #   The bucket policy is read from the file called crl_bucket_policy.json       #
        #################################################################################
        current_directory_path = os.path.dirname(os.path.realpath(__file__)) + '/'
        crl_s3_bucket_policy_json = current_directory_path + 'crl_bucket_policy.json'
    
        crl_bucket_policy = json.loads(open(crl_s3_bucket_policy_json, 'rb').read())
        crl_bucket_policy['Statement'][0]['Resource'][0] = unicode("arn:aws:s3:::"+crl_bucket_name+"/*", 'utf_8')
        crl_bucket_policy['Statement'][0]['Resource'][1] = unicode("arn:aws:s3:::"+crl_bucket_name, 'utf_8')
        
        # Set bucket policy CRL S3 bucket
        response = s3_client.put_bucket_policy(
            Bucket=crl_bucket_name,
            Policy=json.dumps(crl_bucket_policy)
        )
        time.sleep(1)
        
       #######################################################################################
       #   Creates the subordinate private certificate authority in AWS Certificate Manager  #
       #   the api returns the arn of the private CA that was created                        #
       #######################################################################################
        response = acm_pca_client.create_certificate_authority(
            CertificateAuthorityConfiguration={
                'KeyAlgorithm': 'RSA_2048',
                'SigningAlgorithm': 'SHA256WITHRSA',
                'Subject': subject
            },
            RevocationConfiguration={
                'CrlConfiguration': {
                    'Enabled': True,
                    'ExpirationInDays': 20,
                    'S3BucketName': crl_bucket_name
                }
            },
            CertificateAuthorityType='SUBORDINATE',
            IdempotencyToken='builder-subordinate'
        )
        
        subordinate_pca_arn = response['CertificateAuthorityArn']
        print "Creating private certificate authority\n"
        
        #############################################################################################
        #   The infinite loop exists to make sure that the subordinate certificate authority        #
        #   creation is complete and the status is PENDING_CERTIFICATE which means the subordinate  #
        #   CA can now be signed by your organization's root cert                                   #
        #############################################################################################
        while True:
            response = acm_pca_client.describe_certificate_authority(
                CertificateAuthorityArn=subordinate_pca_arn
            )
            
            if response['CertificateAuthority']['Status'] == 'PENDING_CERTIFICATE':
                print "\nPrivate CA has been created"
                print "Please generate the CSR and get it signed by your organizations's root cert"
                break
            else:
                print "*"
                continue
            break
            
        print "\nSuccess : The ARN of the subordinate private certificate authority is : \n" + subordinate_pca_arn
        
        ssm_client.put_parameter(Name='/dp-workshop/subordinate_pca_arn',Type='String',Value=subordinate_pca_arn)
        ssm_client.put_parameter(Name='/dp-workshop/subordinate_ca_serial_number',Type='String',Value=str(subordinate_ca_serial_number))

        print "\nStep-2 has been successfully completed \n"
    except:
        print "Unexpected error:", sys.exc_info()[0]
        raise
    else:
        exit(0)

if __name__ == "__main__":
    main()
    