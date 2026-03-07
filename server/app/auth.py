"""OAuth 2.0 Authorization for the API server"""
import os
import jwt
from typing import Optional
from fastapi import HTTPException
from jwt import PyJWKClient
from app.config import settings
from app.logger import logger


class OAuth2Authorization:
    """OAuth 2.0 authorization handler for the API server"""
    
    def __init__(self):
        # Auth0 configuration
        self.auth0_domain = settings.auth0_domain or os.getenv("AUTH0_DOMAIN")
        self.auth0_audience = settings.auth0_audience or os.getenv("AUTH0_AUDIENCE")
        
        # Resource server configuration
        self.server_url = settings.server_url or os.getenv("SERVER_URL")
        
        if self.auth0_domain and self.auth0_audience:
            # Initialize JWKS client for token validation
            jwks_url = f"https://{self.auth0_domain}/.well-known/jwks.json"
            self.jwks_client = PyJWKClient(jwks_url)
            logger.info("OAuth2 authorization initialized", {"auth0_domain": self.auth0_domain})
        else:
            self.jwks_client = None
            logger.warn("AUTH0_DOMAIN or AUTH0_AUDIENCE not set - authorization disabled")
    
    def is_enabled(self) -> bool:
        """Check if authorization is enabled"""
        return self.auth0_domain is not None and self.auth0_audience is not None
    
    def get_protected_resource_metadata(self) -> dict:
        """
        Returns OAuth 2.0 Protected Resource Metadata per RFC 9728
        This advertises the authorization server to API clients
        """
        if not self.is_enabled():
            return {}
        
        return {
            "resource": self.server_url,
            "authorization_servers": [
                f"https://{self.auth0_domain}"
            ],
            # Optional: Bearer token parameters
            "bearer_methods_supported": [
                "header"
            ],
            # Optional: Token introspection endpoint
            "resource_documentation": f"{self.server_url}/docs",
        }
    
    def get_www_authenticate_header(self, realm: str = "API Server") -> str:
        """
        Generate WWW-Authenticate header for 401 responses per RFC 9728
        This tells the client where to find the resource metadata
        """
        if not self.is_enabled():
            return f'Bearer realm="{realm}"'
        
        # RFC 9728 format with resource metadata URL
        metadata_url = f"{self.server_url}/.well-known/oauth-protected-resource"
        return (
            f'Bearer realm="{realm}", '
            f'as_uri="https://{self.auth0_domain}", '
            f'resource="{metadata_url}"'
        )
    
    async def validate_token(self, authorization: Optional[str]) -> Optional[dict]:
        """
        Validate OAuth 2.0 Bearer token
        
        Returns:
            dict: Token payload if valid
            None: If authorization is disabled or no token provided
        
        Raises:
            HTTPException: If token is invalid
        """
        if not self.is_enabled():
            # Authorization is disabled - allow request
            return None
        
        if not authorization:
            raise HTTPException(
                status_code=401,
                detail="Missing authorization header",
                headers={"WWW-Authenticate": self.get_www_authenticate_header()}
            )
        
        # Extract Bearer token
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Invalid authorization header format. Expected: Bearer <token>",
                headers={"WWW-Authenticate": self.get_www_authenticate_header()}
            )
        
        token = parts[1]
        
        try:
            # Get signing key from JWKS
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            
            # Decode and validate token
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.auth0_audience,
                issuer=f"https://{self.auth0_domain}/"
            )
            
            logger.debug("Token validated", {"subject": payload.get('sub')})
            return payload
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=401,
                detail="Token has expired",
                headers={"WWW-Authenticate": self.get_www_authenticate_header()}
            )
        except jwt.InvalidAudienceError:
            raise HTTPException(
                status_code=401,
                detail="Invalid token audience - token not intended for this server",
                headers={"WWW-Authenticate": self.get_www_authenticate_header()}
            )
        except jwt.InvalidIssuerError:
            raise HTTPException(
                status_code=401,
                detail="Invalid token issuer",
                headers={"WWW-Authenticate": self.get_www_authenticate_header()}
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid token: {str(e)}",
                headers={"WWW-Authenticate": self.get_www_authenticate_header()}
            )
        except Exception as e:
            logger.error("Token validation error", {"error": str(e)})
            raise HTTPException(
                status_code=401,
                detail="Token validation failed",
                headers={"WWW-Authenticate": self.get_www_authenticate_header()}
            )
    


# Global authorization instance
oauth2_auth = OAuth2Authorization()
