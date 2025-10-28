// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { Construct } from "constructs";
import * as cognito from 'aws-cdk-lib/aws-cognito';
import { ResourceNaming } from '../naming';
import { RemovalPolicy, Stack } from "aws-cdk-lib";

/**
 * Properties for the CognitoConfig construct
 */
export interface CognitoConfigProps {
  /**
   * User pool name
   */
  userPoolName?: string;
  
  /**
   * Password policy
   */
  passwordPolicy?: cognito.PasswordPolicy;
  
  /**
   * MFA configuration
   */
  mfa?: cognito.Mfa;
  
  /**
   * Callback URLs for OAuth
   */
  callbackUrls: string[];
  
  /**
   * Logout URLs for OAuth
   */
  logoutUrls?: string[];
  
  /**
   * Whether to set API Gateway scopes
   */
  setAPIGWScopes?: boolean;
  
  /**
   * System admin email
   */
  systemAdminEmail?: string;
}

/**
 * A construct that creates a standardized Cognito configuration
 */
export class CognitoConfig extends Construct {
  /**
   * The Cognito user pool
   */
  public readonly userPool: cognito.UserPool;
  
  /**
   * The Cognito user pool client
   */
  public readonly userPoolClient: cognito.UserPoolClient;
  
  /**
   * The user client ID
   */
  public readonly userClientId: string;
  
  /**
   * The well-known endpoint URL
   */
  public readonly wellKnownEndpointUrl: string;
  
  /**
   * The token endpoint
   */
  public readonly tokenEndpoint: string;
  
  /**
   * The authorization server
   */
  public readonly authorizationServer: string;
  
  constructor(scope: Construct, id: string, props: CognitoConfigProps) {
    super(scope, id);
    
    const stack = Stack.of(this);
    const naming = new ResourceNaming(stack);
    
    // Create user pool
    this.userPool = new cognito.UserPool(this, 'UserPool', {
      userPoolName: props.userPoolName || naming.resourceName('user-pool'),
      selfSignUpEnabled: true,
      autoVerify: { email: true },
      passwordPolicy: props.passwordPolicy || {
        minLength: 8,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      mfa: props.mfa || cognito.Mfa.OPTIONAL,
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    
    // Create domain
    const domain = this.userPool.addDomain('CognitoDomain', {
      cognitoDomain: {
        domainPrefix: `${naming.resourceName('auth')}-${stack.account.substring(0, 8)}`,
      },
    });
    
    // Create user pool client
    this.userPoolClient = new cognito.UserPoolClient(this, 'UserPoolClient', {
      userPool: this.userPool,
      authFlows: {
        userPassword: true,
        userSrp: true,
        adminUserPassword: true,
      },
      oAuth: {
        callbackUrls: props.callbackUrls,
        logoutUrls: props.logoutUrls || props.callbackUrls,
        flows: {
          authorizationCodeGrant: true,
          implicitCodeGrant: true,
        },
        scopes: props.setAPIGWScopes === false ? 
          [cognito.OAuthScope.EMAIL, cognito.OAuthScope.OPENID, cognito.OAuthScope.PROFILE] :
          [cognito.OAuthScope.EMAIL, cognito.OAuthScope.OPENID, cognito.OAuthScope.PROFILE, cognito.OAuthScope.COGNITO_ADMIN],
      },
      supportedIdentityProviders: [
        cognito.UserPoolClientIdentityProvider.COGNITO,
      ],
    });
    
    // Create system admin user if email is provided
    if (props.systemAdminEmail) {
      const cfnUserPool = this.userPool.node.defaultChild as cognito.CfnUserPool;
      
      const adminUserGroup = new cognito.CfnUserPoolGroup(this, 'AdminGroup', {
        userPoolId: this.userPool.userPoolId,
        groupName: 'Admins',
        description: 'Administrator group',
      });
      
      const adminUser = new cognito.CfnUserPoolUser(this, 'AdminUser', {
        userPoolId: this.userPool.userPoolId,
        username: props.systemAdminEmail,
        desiredDeliveryMediums: ['EMAIL'],
        userAttributes: [
          {
            name: 'email',
            value: props.systemAdminEmail,
          },
          {
            name: 'email_verified',
            value: 'true',
          },
        ],
      });
      
      const adminUserToGroup = new cognito.CfnUserPoolUserToGroupAttachment(this, 'AdminUserToGroup', {
        userPoolId: this.userPool.userPoolId,
        groupName: adminUserGroup.groupName || 'Admins', // Fallback to 'Admins' if undefined
        username: adminUser.username || props.systemAdminEmail, // Fallback to email if undefined
      });
    }
    
    // Set properties
    this.userClientId = this.userPoolClient.userPoolClientId;
    this.wellKnownEndpointUrl = `https://cognito-idp.${stack.region}.amazonaws.com/${this.userPool.userPoolId}/.well-known/openid-configuration`;
    this.tokenEndpoint = `https://${domain.domainName}.auth.${stack.region}.amazoncognito.com/oauth2/token`;
    this.authorizationServer = this.tokenEndpoint.substring(0, this.tokenEndpoint.indexOf('/oauth2/token'));
  }
}